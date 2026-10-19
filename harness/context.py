"""Context assembly. Isolation is structural: unknown facts are never in the input,
so there is nothing to annotate and nothing to leak. NPC context is rendered from the same
derivation that backs the per-character memory files (memory.py).

Names are knowledge (task 14): every person is rendered as the *viewer* refers to them, by name
only when the viewer has learned it (`harness/names.py`), otherwise by what can be seen of them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .agents import Intents
from .eventlog import EventLog
from .facts import FactStore
from .glossary import Glossary
from .memory import CharacterMemory, MemoryDeriver
from .models import (
    ACTION, CORRECTION, PLAYER, SCENE_ENTRY, UTTERANCE, WITNESSED, CharacterProfile, Event, Fact, Knower,
    Scene, format_time,
)
from .names import Names
from .providers import Messages
from .state import LiveState
from .style import Style

SAID_LIMIT = 8  # own lines shown as "already said in this scene"
SAID_CHARS = 220  # each shortened to this
CORRECTIONS_SHOWN = 5


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
    character: str = ""

    def messages(self, heard_lines: Sequence[str] = (), notes: Sequence[str] = ()) -> Messages:
        """`notes`: extra lines for a retry (what the last try got wrong)."""
        seen = [*self.seen, *heard_lines]
        parts = [*self.sections]
        if seen:
            parts.append("Recent conversation:\n" + "\n".join(seen))
        parts.extend(notes)
        parts.append(self.instruction)
        return self.finish([
            {"role": "system", "content": self.system},
            {"role": "user", "content": "\n\n".join(parts)},
        ])

    def heard_text(self, heard_lines: Sequence[str] = ()) -> str:
        """Words this character has heard lately (for the name check: a name said in front of
        them is a name they have heard)."""
        return "\n".join([*self.seen, *heard_lines])

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
        names: Names | None = None,
        style: Style | None = None,
    ) -> None:
        """`language`: what the player reads (narration, NPC speech). `record_language`: what
        the extractor writes facts in. None: no instruction (the model's own choice).
        `glossary`: every rendered context goes through it (one form of each name) and each prompt
        lists the names it mentions. `narration`: "prose" (free text) or "json" (task 3).
        `names`: who knows whose name; None means everyone knows everyone.
        `style`: the Sapkowski-style wording and exemplars (harness/style.py); None keeps the
        task 12 prompts."""
        self.style = style
        self.language, self.record_language = language, record_language
        self.glossary, self.narration = glossary, narration
        self.names = names
        self.log, self.facts, self.intents = log, facts, intents
        self.profiles, self.live, self.deriver = profiles, live, deriver
        self.history_limit = history_limit

    # -- names ------------------------------------------------------------------------------
    def name(self, cid: str) -> str:
        """The real name (code-side use, judges). A viewer's text uses `ref`."""
        p = self.profiles.get(cid)
        return p.name if p else cid

    def ref(self, viewer: str | None, cid: str, before: int | None = None) -> str:
        """How `viewer` refers to `cid`: the name if the viewer knows it, else what they see."""
        return self.names.ref(viewer, cid, before) if self.names else self.name(cid)

    def label(self, viewer: str | None, cid: str, before: int | None = None) -> str:
        """`ref` for display (first letter capital): the speaker label in the player's feed."""
        r = self.ref(viewer, cid, before)
        return r[:1].upper() + r[1:]

    def mask(self, viewer: str | None, text: str,
             known: frozenset[str] | None = None) -> str:
        """A record's text with the names `viewer` does not know replaced by their appearance."""
        return self.names.mask(viewer, text, known=known) if self.names else text

    def describe(self, cid: str) -> str:
        """For code-side judges and listers: the real name, with the appearance if hidden."""
        return self.names.describe(cid) if self.names else self.name(cid)

    def finish(self, messages: Messages, viewer: str | None = None,
               known: frozenset[str] | None = None) -> Messages:
        """Last step of every render: one form of each name, and the names the prompt mentions
        appended to the system message. Only names `viewer` knows are offered (None: all). `known`:
        a snapshot of the ids whose names the viewer knows (a worker thread must not read the
        database; default: read it now)."""
        g = self.glossary
        if g is None and viewer is None:
            return messages
        msgs = messages
        if g is not None:  # note: the glossary also rewrites ids such as "horst" to "Горст"
            msgs = [{**m, "content": g.apply(m["content"])} for m in msgs]
        if viewer is not None:  # safety net: a name the viewer does not know never gets through
            msgs = [{**m, "content": self.mask(viewer, m["content"], known=known)} for m in msgs]
        if g is None:
            return msgs
        if self.names is None:
            ids = list(self.profiles)
        elif viewer is None:
            ids = list(self.profiles)
        else:
            k = self.names.known_set(viewer) if known is None else known
            ids = [c for c in self.profiles if c == viewer or c in k or not self.names.hidden(c)]
        line = g.prompt_line("\n".join(m["content"] for m in msgs),
                             [self.name(c) for c in ids if c in self.profiles])
        if line:
            msgs[0] = {**msgs[0], "content": msgs[0]["content"] + " " + line}
        return msgs

    # -- shared renderers ---------------------------------------------------------------------
    def _line(self, e: Event, viewer: str | None = None) -> str:
        # `speech`: the spoken part of a line with the speaker's own beats (task 15); the beats
        # are separate action events, so they are not repeated here
        return f"{self.ref(viewer, e.payload['speaker'], e.id)}: {e.payload.get('speech', e.payload['text'])}"

    def _scene_header(self, scene: Scene, viewer: str | None = None) -> str:
        """viewer None: the omniscient view (judges): names with appearances."""
        if viewer is None:
            who = ", ".join(self.describe(c) for c in scene.present)
        else:
            who = ", ".join(self.ref(viewer, c) + (" (you)" if c == viewer else "")
                            for c in scene.present)
        return f"Location: {scene.location}\nTime: {format_time(scene.time)}\nPresent: {who}"

    def _known(self, f: Fact, k: Knower, viewer: str) -> str:
        """A knowledge line; second-hand knowledge carries its source."""
        text = self.mask(viewer, f.content)
        if k.source == "own life":
            return f"- {text} (from your own life)"
        if k.source is not None:
            return f"- {text} (heard from {self.ref(viewer, k.source)})"
        return f"- {text}"

    def _seen(self, e: Event, viewer: str | None = None) -> str:
        if e.type == ACTION:
            actor = e.payload.get("actor")
            if actor:  # the player's own action, as written
                return f"[you see] {self.ref(viewer, actor, e.id)} does: {e.payload['text']}"
            return f"[you see] {self.mask(viewer, e.payload['text'])}"
        return self._line(e, viewer)

    # -- NPC ---------------------------------------------------------------------------------
    def knowledge_lines(self, mem: CharacterMemory) -> list[str]:
        return [self._known(it.fact, it.knower, mem.character) for it in mem.knows]

    def character(self, character: str, scene: Scene, mem: CharacterMemory | None = None
                  ) -> Messages:
        return self.character_view(character, scene, mem).messages()

    def corrections(self, character: str | None = None) -> list[str]:
        """The player's notes on model errors (stored per campaign), newest last: a line by
        `character` that the player marked as impossible, with the player's reason."""
        out = []
        for e in self.log.active([CORRECTION]):
            if character is not None and e.payload.get("npc") not in (None, character):
                continue
            out.append(f"- \"{e.payload.get('line', '')[:200]}\" was wrong: "
                       f"{e.payload.get('explanation') or 'the character could not know this'}")
        return out[-CORRECTIONS_SHOWN:]

    def _already_said(self, character: str, mem: CharacterMemory, viewer: str
                      ) -> list[str]:
        """What `character` has already said in this scene: its own recent lines (short) and the
        points those lines made (facts extracted from them), so it moves the talk on instead of
        saying the same thing in new words."""
        start = max((e.id for e in self.log.active([SCENE_ENTRY])), default=0)
        own_all = [e for e in self.log.active([UTTERANCE])
                   if e.payload.get("speaker") == character and e.id > start]
        own = own_all[-SAID_LIMIT:]
        if not own:
            return []
        short = []
        for e in own:
            t = e.payload["text"].strip()
            short.append(f"- {t if len(t) <= SAID_CHARS else t[:SAID_CHARS].rsplit(' ', 1)[0] + '...'}")
        out = ["What you have already said in this scene (do not say the same again, not even "
               "in other words; move the conversation on):\n" + "\n".join(short)]
        ids = {e.id for e in own_all}
        points = [it.fact.content for it in mem.knows
                  if it.fact.source_event_id in ids and it.knower.how == WITNESSED]
        if points:
            out.append("Points you have already made:\n" + "\n".join(
                f"- {self.mask(viewer, p)}" for p in points[-SAID_LIMIT:]))
        return out

    def character_view(self, character: str, scene: Scene, mem: CharacterMemory | None = None
                       ) -> NpcView:
        prof = self.profiles.get(character) or CharacterProfile(character, character)
        mem = mem or self.deriver.derive(character, scene.time)
        seen = self.log.recent_dialogue(witnessed_by=character, limit=self.history_limit)

        known_names = self.names.known_set(character) if self.names else frozenset()
        parts = [self._scene_header(scene, character)]
        if mem.knows:
            parts.append("What you know:\n" + "\n".join(self.knowledge_lines(mem)))
        if mem.state:
            parts.append("Your own condition:\n" + "\n".join(
                f"- {e.category}: {e.item}" for e in mem.state))
        if mem.noticed:
            parts.append("You have just noticed:\n" + "\n".join(
                f"- {self.mask(character, f.content)}" for _, f in mem.noticed))
        if mem.attitudes:
            parts.append("How you feel about it:\n" + "\n".join(
                f"- {a.stance} ({a.magnitude:g}): {self.mask(character, f.content)}"
                for a, f in mem.attitudes))
        parts.extend(self._already_said(character, mem, character))
        if mem.intents:
            parts.append(
                "Things you meant to say and have not yet said:\n"
                + "\n".join(f"- {e.payload['text']}" for e in mem.intents)
            )
        notes = self.corrections(character)
        if notes:
            parts.append("The player has pointed out mistakes in earlier lines; do not repeat "
                         "them:\n" + "\n".join(notes))
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
        known = (self.knowledge_lines(mem) + [self._seen(e, character) for e in seen]
                 + [f"- (own condition) {e.category}: {e.item}" for e in mem.state]
                 + [f"- (just noticed) {self.mask(character, f.content)}"
                    for _, f in mem.noticed])
        return NpcView(
            system=system, sections=parts,
            seen=[self._seen(e, character) for e in seen], instruction=instruction, known=known,
            name=prof.name, character=character,
            finish=lambda m, c=character, k=known_names: self.finish(m, c, k))

    def heard_line(self, viewer: str, speaker: str, text: str) -> str:
        return f"{self.ref(viewer, speaker)}: {text}"

    # -- narrator ----------------------------------------------------------------------------
    def narrator(self, scene: Scene, player_input: str) -> Messages:
        """The narrator speaks from the player character's perception (`PLAYER` below is the
        viewer): a person whose name the player character has not learned is only described."""
        campaign = self.facts.all_campaign(scene.time)
        canon = self.facts.search_canon(
            player_input + " " + scene.location + " " + " ".join(f.content for f in campaign[-5:])
        )
        recent = self.log.recent_dialogue(limit=self.history_limit, include_narration=True)
        snap = self.live.snapshot()
        m = lambda t: self.mask(PLAYER, t)  # noqa: E731

        def fmt(e: Event) -> str:
            if e.type == UTTERANCE:
                return self._line(e, PLAYER)
            if e.type == ACTION and e.payload.get("actor"):
                return f"[action] {self.ref(PLAYER, e.payload['actor'], e.id)}: {e.payload['text']}"
            return f"[{e.type}] {m(e.payload['text'])}"

        parts = [self._scene_header(scene, PLAYER)]
        if canon:
            parts.append("Relevant canon:\n" + "\n".join(f"- {m(f.content)}" for f in canon))
        if campaign:
            parts.append("Campaign state:\n" + "\n".join(f"- {m(f.content)}" for f in campaign))
        state_lines = [
            f"- {self.ref(PLAYER, c)}: {cat}: {item} ({'observable' if obs else 'hidden'})"
            for c in scene.present
            for (cat, item), obs in snap.get(c, {}).items()
        ]
        if state_lines:
            parts.append("Character state:\n" + "\n".join(state_lines))
        if recent:
            parts.append("Recent events:\n" + "\n".join(fmt(e) for e in recent))
        npcs = ", ".join(f"{c} ({self.ref(PLAYER, c)})" for c in scene.present if c != PLAYER)
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
            ], PLAYER)
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
        ], PLAYER)

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

        names = [self.describe(c) for c in scene.present]
        g = self.glossary
        return actions_messages(
            narration, names=names, language=self.record_language,
            glossary_line=g.prompt_line(narration, [self.name(c) for c in scene.present])
            if g else "", limit=limit)

    # -- extractor ---------------------------------------------------------------------------
    def extractor(self, scene: Scene, segments: list[tuple[str, str]]) -> Messages:
        """segments: (source key, text). Asks for a JSON diff: fact text + source + notability,
        and live-state changes. Knowers are not asked for: code computes perception."""
        who = ", ".join(scene.present + scene.outside)
        names = [self.describe(c) for c in scene.present + scene.outside]
        keys = ", ".join(k for k, _ in segments)
        body = "\n".join(f"[{k}] {t}" for k, t in segments)
        snap = self.live.snapshot()
        cur = [
            f"- {c}: {cat}: {item} ({'observable' if obs else 'hidden'})"
            for c, elems in snap.items()
            for (cat, item), obs in elems.items()
        ]
        hidden = self.names and any(self.names.hidden(c) for c in scene.present + scene.outside)
        instr = (
            "Extract new facts and live-state changes from the passages below as JSON, "
            "nothing else:\n"
            '{"new_facts": [{"content": str, "source": <one of: ' + keys + '>, '
            '"notability": number 0..1, "location": optional str}],\n'
            ' "state_changes": [{"character": <id>, "category": "injury"|"clothing"|"inventory"|'
            '"equipment"|"internal"|"appearance", "op": "add"|"remove"|"reveal"|"hide", "item": str, '
            '"observable": true|false, "source": <segment>}]}\n'
            f"Characters: {who}. Do not say who knows or saw a fact; that is decided elsewhere. "
            '"remove" only works on an item the character currently has; "reveal"/"hide" change '
            "whether an existing item is observable. Do not emit any other keys.\n"
            + (f"Names (a passage may describe a person without naming them; in facts, use the "
               f"name): {'; '.join(names)}.\n" if hidden else "")
            + (f"Write every fact's content and every state item in {self.record_language}"
               + ("; names, places and titles stay in Ukrainian as they are written. "
                  if self.glossary else ". ") if self.record_language else "")
            + "Current state:\n" + ("\n".join(cur) if cur else "- (none)")
        )
        return self.finish([
            {"role": "system", "content": "You are a precise fact extractor."},
            {"role": "user", "content": instr + "\n\n" + body},
        ])
