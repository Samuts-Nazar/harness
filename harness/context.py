"""Context assembly. Isolation is structural: unknown facts are never in the input,
so there is nothing to annotate and nothing to leak."""
from __future__ import annotations

from .agents import Intents
from .eventlog import EventLog
from .facts import FactStore
from .models import UTTERANCE, CharacterProfile, Event, Scene, format_time
from .providers import Messages


class ContextBuilder:
    def __init__(
        self,
        log: EventLog,
        facts: FactStore,
        intents: Intents,
        profiles: dict[str, CharacterProfile],
        history_limit: int = 10,
    ) -> None:
        self.log, self.facts, self.intents = log, facts, intents
        self.profiles = profiles
        self.history_limit = history_limit

    def name(self, cid: str) -> str:
        p = self.profiles.get(cid)
        return p.name if p else cid

    def _line(self, e: Event) -> str:
        return f"{self.name(e.payload['speaker'])}: {e.payload['text']}"

    def _scene_header(self, scene: Scene) -> str:
        who = ", ".join(self.name(c) for c in scene.present)
        return f"Location: {scene.location}\nTime: {format_time(scene.time)}\nPresent: {who}"

    def character(self, character: str, scene: Scene) -> Messages:
        prof = self.profiles.get(character) or CharacterProfile(character, character)
        known = self.facts.visible_to(character, scene.time)
        own = [
            e
            for e in self.log.active([UTTERANCE])
            if e.payload.get("speaker") == character
        ][-self.history_limit :]
        pending = self.intents.pending(character)
        seen = self.log.recent_dialogue(witnessed_by=character, limit=self.history_limit)

        parts = [self._scene_header(scene)]
        if known:
            parts.append("What you know:\n" + "\n".join(f"- {f.content}" for f in known))
        if own:
            parts.append(
                "What you have said before:\n" + "\n".join(f"- {e.payload['text']}" for e in own)
            )
        if pending:
            parts.append(
                "Things you meant to say and have not yet said:\n"
                + "\n".join(f"- {e.payload['text']}" for e in pending)
            )
        if seen:
            parts.append("Recent conversation:\n" + "\n".join(self._line(e) for e in seen))
        parts.append(f"Say what {prof.name} says next, aloud and in character. Dialogue only.")
        system = f"You are {prof.name}. {prof.description}".strip()
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(parts)},
        ]

    def narrator(self, scene: Scene, player_input: str) -> Messages:
        campaign = self.facts.all_campaign(scene.time)
        canon = self.facts.search_canon(
            player_input + " " + scene.location + " " + " ".join(f.content for f in campaign[-5:])
        )
        recent = self.log.recent_dialogue(limit=self.history_limit, include_narration=True)

        def fmt(e: Event) -> str:
            return self._line(e) if e.type == UTTERANCE else f"[narration] {e.payload['text']}"

        parts = [self._scene_header(scene)]
        if canon:
            parts.append("Relevant canon:\n" + "\n".join(f"- {f.content}" for f in canon))
        if campaign:
            parts.append("Campaign state:\n" + "\n".join(f"- {f.content}" for f in campaign))
        if recent:
            parts.append("Recent events:\n" + "\n".join(fmt(e) for e in recent))
        parts.append(f"The player does/says: {player_input}\nNarrate what happens next.")
        system = (
            "You are the narrator of a role-playing game. Write vivid prose. "
            "Do not write dialogue for characters other than the player."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(parts)},
        ]

    def extractor(
        self, scene: Scene, segments: list[tuple[str, str]]
    ) -> Messages:
        """segments: (source key, text). Asks for a JSON diff of new facts."""
        present = ", ".join(scene.present)
        keys = ", ".join(k for k, _ in segments)
        body = "\n".join(f"[{k}] {t}" for k, t in segments)
        instr = (
            "Extract new facts from the passages below as JSON, nothing else:\n"
            '{"new_facts": [{"content": str, "source": <one of: ' + keys + '>, '
            '"knowers": [{"character": <id>, "how": "witnessed"|"heard"|"told"}], '
            '"notability": number 0..1, "location": optional str}]}\n'
            f"Character ids allowed as knowers (only those present): {present}.\n"
            "Do not emit any other keys."
        )
        return [
            {"role": "system", "content": "You are a precise fact extractor."},
            {"role": "user", "content": instr + "\n\n" + body},
        ]
