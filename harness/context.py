"""Context assembly. Isolation is structural: unknown facts are never in the input,
so there is nothing to annotate and nothing to leak. NPC context is rendered from the same
derivation that backs the per-character memory files (memory.py)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .agents import Intents
from .eventlog import EventLog
from .facts import FactStore
from .glossary import Glossary
from .memory import CharacterMemory, MemoryDeriver
from .models import ACTION, UTTERANCE, CharacterProfile, Event, Fact, Knower, Scene, format_time
from .providers import Messages
from .state import LiveState
from .style import Style


@dataclass
class NpcView:
    """An NPC's context, read from the database once (main thread). `messages(heard_lines)`
    renders it without touching the database, so a worker can add what other NPCs said earlier in
    the same turn. `known` is what the output check treats as the character's knowledge."""
    system: str
    sections: list[str]
    seen: list[str]
    instruction: str
    known: list[str]
    name: str
    finish: Callable[[Messages], Messages]

    def messages(self, heard_lines: Sequence[str] = ()) -> Messages:
        seen = [*self.seen, *heard_lines]
        parts = [*self.sections]
        if seen:
            parts.append("Recent conversation:\n" + "\n".join(seen))
        parts.append(self.instruction)
        return self.finish([
            {"role": "system", "content": self.system},
            {"role": "user", "content": "\n\n".join(parts)},
        ])

    def check_prefix(self, heard_lines: Sequence[str] = ()) -> str:
        known = [*self.known, *heard_lines]
        return (f"Character: {self.name}\nWhat the character knows:\n"
                + ("\n".join(known) or "- (nothing)") + "\nLine: ")


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
        language: str | None = None,
        record_language: str | None = None,
        glossary: Glossary | None = None,
        narration: str = "json",
        style: Style | None = None,
    ) -> None:
        """`language`: what the player reads (narration, NPC speech). `record_language`: what
        the extractor writes facts in. None: no instruction (the model's own choice).
        `glossary`: every rendered context goes through it (one form of each name) and each prompt
        lists the names it mentions. `narration`: "prose" (free text) or "json" (task 3).
        `style`: the Sapkowski-style wording and exemplars (harness/style.py); None keeps the
        task 12 prompts."""
        self.style = style
        self.language, self.record_language = language, record_language
        self.glossary, self.narration = glossary, narration
        self.log, self.facts, self.intents = log, facts, intents
        self.profiles, self.live, self.deriver = profiles, live, deriver
        self.history_limit = history_limit

    def name(self, cid: str) -> str:
        p = self.profiles.get(cid)
        return p.name if p else cid

    def finish(self, messages: Messages) -> Messages:
        """Last step of every render: one form of each name, and the names the prompt mentions
        appended to the system message."""
        g = self.glossary
        if g is None:
            return messages
        msgs = [{**m, "content": g.apply(m["content"])} for m in messages]
        line = g.prompt_line("\n".join(m["content"] for m in msgs),
                             [p.name for p in self.profiles.values()])
        if line:
            msgs[0] = {**msgs[0], "content": msgs[0]["content"] + " " + line}
        return msgs

    def _line(self, e: Event) -> str:
        # `speech`: the spoken part of a line with the speaker's own beats (task 15); the beats
        # are separate action events, so they are not repeated here
        return f"{self.name(e.payload['speaker'])}: {e.payload.get('speech', e.payload['text'])}"

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
        return self.character_view(character, scene, mem).messages()

    def character_view(self, character: str, scene: Scene, mem: CharacterMemory | None = None
                       ) -> NpcView:
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
        instruction = (
            f"Say what {prof.name} says next, aloud and in character. Write only {prof.name}'s "
            "own words as one continuous speech: no stage directions, no other characters' lines."
            + (f" Speak in {self.language}." if self.language else "")
        )
        system = f"You are {prof.name}. {prof.description}".strip()
        if self.style is not None:
            system = self.style.npc_system(prof)
            instruction = self.style.npc_instruction(prof, self.language)
            examples = self.style.npc_examples_section(" ".join([
                scene.location, prof.description, *(e.payload["text"] for e in seen[-2:]),
                *(it.fact.content for it in mem.knows[-4:])]))
            if examples:
                parts.append(examples)
        known = (self.knowledge_lines(mem) + [self._seen(e) for e in seen]
                 + [f"- (own condition) {e.category}: {e.item}" for e in mem.state]
                 + [f"- (just noticed) {f.content}" for _, f in mem.noticed])
        return NpcView(
            system=system, sections=parts,
            seen=[self._seen(e) for e in seen], instruction=instruction, known=known,
            name=prof.name, finish=self.finish)

    def heard_line(self, speaker: str, text: str) -> str:
        return f"{self.name(speaker)}: {text}"

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
        if self.narration == "prose":
            parts.append(
                f"The player does/says: {player_input}\nNarrate what happens next.\n\n"
                "Write the narration as plain prose and nothing else: no JSON, no lists, no "
                "headings, no markup. Its length and shape follow the moment (a glance can be a "
                "sentence, a crisis several paragraphs); do not settle into a fixed pattern. "
                "Never write speech for anyone but the player: NPC lines are produced "
                "separately, so no quotation marks and no dialogue dashes; show what a "
                "character does, not what they say. Do not decide what the player character says, does or feels beyond "
                "what the player gave."
                + (f"\nWrite in {self.language}." if self.language else ""))
            system = "You are the narrator of a role-playing game. Write vivid prose."
            if self.style is not None:
                system = self.style.narrator_system()
                examples = self.style.narrator_examples_section(" ".join([
                    scene.location, player_input, *(f.content for f in campaign[-3:])]))
                if examples:
                    parts.insert(-1, examples)
            return self.finish([
                {"role": "system", "content": system},
                {"role": "user", "content": "\n\n".join(parts)},
            ])
        parts.append(
            f"The player does/says: {player_input}\nNarrate what happens next.\n\n"
            "Reply with ONE JSON object and nothing else:\n"
            '{"description": <scene prose, no quoted speech>,\n'
            ' "observable_actions": [<one short sentence per thing a character does that anyone '
            "in the room could see or hear, naming the actor>],\n"
            f' "speakers": [<ids (the word before the parentheses) of characters who speak next, '
            f"only from: {npcs}>]}}\n"
            "Never write speech for anyone but the player: NPC lines are produced separately."
            + (f"\nWrite the description and the observable actions in {self.language}; "
               "keep the JSON keys and the speaker ids as they are." if self.language else "")
        )
        system = "You are the narrator of a role-playing game. Write vivid prose."
        return self.finish([
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(parts)},
        ])

    # -- director ----------------------------------------------------------------------------
    def director_state(self, scene: Scene, player_input: str, narration: str) -> list[str]:
        """What the speaker decider sees: the scene, the latest exchange, the narration."""
        recent = self.log.recent_dialogue(limit=4)
        lines = [self._scene_header(scene)]
        if recent:
            lines.append("Recent:\n" + "\n".join(self._seen(e) for e in recent))
        lines += [f"The player does/says: {player_input}", f"Narration: {narration}"]
        g = self.glossary
        return [g.apply(x) for x in lines] if g else lines

    def actions(self, narration: str, scene: Scene, limit: int = 6) -> Messages:
        from .director import actions_messages

        names = [self.name(c) for c in scene.present]
        g = self.glossary
        return actions_messages(
            narration, names=names, language=self.record_language,
            glossary_line=g.prompt_line(narration, names) if g else "", limit=limit)

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
            + (f"Write every fact's content and every state item in {self.record_language}"
               + ("; names, places and titles stay in Ukrainian as they are written. "
                  if self.glossary else ". ") if self.record_language else "")
            + "Current state:\n" + ("\n".join(cur) if cur else "- (none)")
        )
        return self.finish([
            {"role": "system", "content": "You are a precise fact extractor."},
            {"role": "user", "content": instr + "\n\n" + body},
        ])
