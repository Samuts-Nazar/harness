"""Context assembly. Isolation is structural: unknown facts are never in the input,
so there is nothing to annotate and nothing to leak. NPC context is rendered from the same
derivation that backs the per-character memory files (memory.py)."""
from __future__ import annotations

from .agents import Intents
from .eventlog import EventLog
from .facts import FactStore
from .memory import CharacterMemory, MemoryDeriver
from .models import ACTION, UTTERANCE, CharacterProfile, Event, Fact, Knower, Scene, format_time
from .providers import Messages
from .state import LiveState


class ContextBuilder:
    def __init__(
        self,
        log: EventLog,
        facts: FactStore,
        intents: Intents,
        profiles: dict[str, CharacterProfile],
        live: LiveState,
        deriver: MemoryDeriver,
        history_limit: int = 10,
    ) -> None:
        self.log, self.facts, self.intents = log, facts, intents
        self.profiles, self.live, self.deriver = profiles, live, deriver
        self.history_limit = history_limit

    def name(self, cid: str) -> str:
        p = self.profiles.get(cid)
        return p.name if p else cid

    def _line(self, e: Event) -> str:
        return f"{self.name(e.payload['speaker'])}: {e.payload['text']}"

    def _scene_header(self, scene: Scene) -> str:
        who = ", ".join(self.name(c) for c in scene.present)
        return f"Location: {scene.location}\nTime: {format_time(scene.time)}\nPresent: {who}"

    def _known(self, f: Fact, k: Knower) -> str:
        """A knowledge line; second-hand knowledge carries its source."""
        if k.source is not None:
            return f"- {f.content} (heard from {self.name(k.source)})"
        return f"- {f.content}"

    # -- NPC ---------------------------------------------------------------------------------
    def knowledge_lines(self, mem: CharacterMemory) -> list[str]:
        return [self._known(it.fact, it.knower) for it in mem.knows]

    def character(self, character: str, scene: Scene, mem: CharacterMemory | None = None
                  ) -> Messages:
        prof = self.profiles.get(character) or CharacterProfile(character, character)
        mem = mem or self.deriver.derive(character, scene.time)
        own = [
            e
            for e in self.log.active([UTTERANCE])
            if e.payload.get("speaker") == character
        ][-self.history_limit :]
        seen = self.log.recent_dialogue(witnessed_by=character, limit=self.history_limit)

        parts = [self._scene_header(scene)]
        if mem.knows:
            parts.append("What you know:\n" + "\n".join(self.knowledge_lines(mem)))
        if mem.state:
            parts.append("Your own condition:\n" + "\n".join(
                f"- {e.category}: {e.item}" for e in mem.state))
        if mem.noticed:
            parts.append("You have just noticed:\n" + "\n".join(
                f"- {f.content}" for _, f in mem.noticed))
        if mem.attitudes:
            parts.append("How you feel about it:\n" + "\n".join(
                f"- {a.stance} ({a.magnitude:g}): {f.content}" for a, f in mem.attitudes))
        if own:
            parts.append(
                "What you have said before:\n" + "\n".join(f"- {e.payload['text']}" for e in own)
            )
        if mem.intents:
            parts.append(
                "Things you meant to say and have not yet said:\n"
                + "\n".join(f"- {e.payload['text']}" for e in mem.intents)
            )
        if seen:
            parts.append("Recent conversation:\n" + "\n".join(self._seen(e) for e in seen))
        parts.append(f"Say what {prof.name} says next, aloud and in character. Dialogue only.")
        system = f"You are {prof.name}. {prof.description}".strip()
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(parts)},
        ]

    def _seen(self, e: Event) -> str:
        return f"[you see] {e.payload['text']}" if e.type == ACTION else self._line(e)

    # -- narrator ----------------------------------------------------------------------------
    def narrator(self, scene: Scene, player_input: str) -> Messages:
        campaign = self.facts.all_campaign(scene.time)
        canon = self.facts.search_canon(
            player_input + " " + scene.location + " " + " ".join(f.content for f in campaign[-5:])
        )
        recent = self.log.recent_dialogue(limit=self.history_limit, include_narration=True)
        snap = self.live.snapshot()

        def fmt(e: Event) -> str:
            if e.type == UTTERANCE:
                return self._line(e)
            return f"[{e.type}] {e.payload['text']}"

        parts = [self._scene_header(scene)]
        if canon:
            parts.append("Relevant canon:\n" + "\n".join(f"- {f.content}" for f in canon))
        if campaign:
            parts.append("Campaign state:\n" + "\n".join(f"- {f.content}" for f in campaign))
        state_lines = [
            f"- {self.name(c)}: {cat}: {item} ({'observable' if obs else 'hidden'})"
            for c in scene.present
            for (cat, item), obs in snap.get(c, {}).items()
        ]
        if state_lines:
            parts.append("Character state:\n" + "\n".join(state_lines))
        if recent:
            parts.append("Recent events:\n" + "\n".join(fmt(e) for e in recent))
        npcs = ", ".join(f"{c} ({self.name(c)})" for c in scene.present if c != "player")
        parts.append(
            f"The player does/says: {player_input}\nNarrate what happens next.\n\n"
            "Reply with ONE JSON object and nothing else:\n"
            '{"description": <scene prose, no quoted speech>,\n'
            ' "observable_actions": [<one short sentence per thing a character does that anyone '
            "in the room could see or hear, naming the actor>],\n"
            f' "speakers": [<ids of characters who speak next, only from: {npcs}>]}}\n'
            "Never write speech for anyone but the player: NPC lines are produced separately."
        )
        system = "You are the narrator of a role-playing game. Write vivid prose."
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(parts)},
        ]

    # -- extractor ---------------------------------------------------------------------------
    def extractor(self, scene: Scene, segments: list[tuple[str, str]]) -> Messages:
        """segments: (source key, text). Asks for a JSON diff: fact text + source + notability,
        and live-state changes. Knowers are not asked for: code computes perception."""
        who = ", ".join(scene.present + scene.outside)
        keys = ", ".join(k for k, _ in segments)
        body = "\n".join(f"[{k}] {t}" for k, t in segments)
        snap = self.live.snapshot()
        cur = [
            f"- {c}: {cat}: {item} ({'observable' if obs else 'hidden'})"
            for c, elems in snap.items()
            for (cat, item), obs in elems.items()
        ]
        instr = (
            "Extract new facts and live-state changes from the passages below as JSON, "
            "nothing else:\n"
            '{"new_facts": [{"content": str, "source": <one of: ' + keys + '>, '
            '"notability": number 0..1, "location": optional str}],\n'
            ' "state_changes": [{"character": <id>, "category": "injury"|"clothing"|"inventory"|'
            '"equipment"|"internal", "op": "add"|"remove"|"reveal"|"hide", "item": str, '
            '"observable": true|false, "source": <segment>}]}\n'
            f"Characters: {who}. Do not say who knows or saw a fact; that is decided elsewhere. "
            '"remove" only works on an item the character currently has; "reveal"/"hide" change '
            "whether an existing item is observable. Do not emit any other keys.\n"
            "Current state:\n" + ("\n".join(cur) if cur else "- (none)")
        )
        return [
            {"role": "system", "content": "You are a precise fact extractor."},
            {"role": "user", "content": instr + "\n\n" + body},
        ]
