"""Context assembly. Isolation is structural: unknown facts are never in the input,
so there is nothing to annotate and nothing to leak. NPC context is rendered from the same
derivation that backs the per-character memory files (memory.py).

Names are knowledge (task 14): every person is rendered as the *viewer* refers to them, by name
only when the viewer has learned it (`harness/names.py`), otherwise by what can be seen of them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Callable, Sequence

from .agents import Intents
from . import items
from .eventlog import EventLog
from .facts import FactStore
from .glossary import Glossary
from .memory import CharacterMemory, MemoryDeriver
from .models import (
    ACTION, CORRECTION, PLAYER, PORTRAIT_LEAK, SCENE_ENTRY, UTTERANCE, WITNESSED, CharacterProfile,
    Event, Fact, Knower,
    Scene, format_time,
)
from .names import Names
from .relations import Relations
from .portrait import MAX_WORDS, Portrait, Situation, Stance, select_stance, slice_text
from .providers import Messages
from .shape import Shape, shape_instruction
from .state import LiveState
from .style import Style

PLAYER_CHARACTER_RULE = (
    "The player character is the player's: never repeat or quote the player's own words (the "
    "screen already shows them) and never write what the player character does, takes, "
    "decides, thinks or wants; write only the world: what is seen, heard, felt in the body, "
    "and what others do. Wrong: «Ти кладеш гаманець до кишені, береш хліб і йдеш до дверей.» "
    "(the player only wrote «Іду на ринок»). Right: «Брук мокрий, попереду шумить ринок; "
    "пахне хлібом.»")


UNLIMITED_NARRATOR = (
    "The player character is a being without limits: whatever the player declares the character "
    "does, happens exactly as declared. Never refuse it, soften it, let it fail or turn it into "
    "an attempt; narrate the world's reaction to it, not whether it works.")
UNLIMITED_EXTRACTOR = (
    "What the player character does, as the player wrote it, has happened: record it as a fact at "
    "full strength, exactly as stated (never 'tries to', 'claims', 'seems to', no hedging, no "
    "smaller scale), and give such an act the notability its scale in the world deserves (a "
    "miracle in front of a crowd is high).")
SAID_LIMIT = 8  # own lines shown as "already said in this scene"
SAID_CHARS = 220  # each shortened to this
CORRECTIONS_SHOWN = 5
OUTCOME_EVENT = "outcome"  # harness/outcome.py (not imported: it imports the judge)
# observable live state that means danger in the room (a drawn blade, a raised crossbow)
DANGER = re.compile(r"\b(?:drawn|оголен\w*|витягнут\w*|наставлен\w*|націлен\w*)", re.IGNORECASE)
# counted in the slice budget (MAX_WORDS for the whole section)
LEAK_TRUST = 0.4  # a hidden-layer leak goes into a portrait NPC's prompt only from this trust on
PORTRAIT_HEAD = "Who you are now (never quote it; example lines show only the voice):"


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
    examples: tuple[str, ...] = ()  # the portrait's example lines in this prompt (copy check)
    # a hidden-layer leak in this prompt and its scene key: used (a PORTRAIT_LEAK event) only
    # when a line or gesture made from it is delivered
    leak: str = ""
    leak_scene: str = ""

    def messages(self, heard_lines: Sequence[str] = (), notes: Sequence[str] = (),
                 instruction: str | None = None) -> Messages:
        """`notes`: extra lines for a retry (what the last try got wrong). `instruction`: replaces
        the closing instruction (a response shape, `ContextBuilder.npc_instruction`)."""
        seen = [*self.seen, *heard_lines]
        parts = [*self.sections]
        if seen:
            parts.append("Recent conversation:\n" + "\n".join(seen))
        parts.extend(notes)
        parts.append(self.instruction if instruction is None else instruction)
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
        player_unlimited: bool = False,
    ) -> None:
        """`player_unlimited` (task 17): what the player declares the character does, happens; the
        narrator and the extractor must not soften it. `language`: what the player reads (narration, NPC speech). `record_language`: what
        the extractor writes facts in. None: no instruction (the model's own choice).
        `glossary`: every rendered context goes through it (one form of each name) and each prompt
        lists the names it mentions. `narration`: "prose" (free text) or "json" (task 3).
        `names`: who knows whose name; None means everyone knows everyone.
        `style`: the Sapkowski-style wording and exemplars (harness/style.py); None keeps the
        task 12 prompts."""
        self.style = style
        self.player_unlimited = player_unlimited
        self.outcomes = False  # set by the engine (harness/outcome.py)
        # set by the engine: the extractor prompt lists item ids and locations and teaches
        # move/realize. Off keeps the old prompt byte for byte, so old recordings still replay.
        self.item_ids = False
        # the player's wishes for the campaign, set at its start (a game package: tone, pace,
        # content limits, notes); shown to the narrator, never above the rules
        self.intent = ""
        # only the content limits of that intent: also for NPC lines and resolution prose
        self.limits = ""
        self.language, self.record_language = language, record_language
        self.glossary, self.narration = glossary, narration
        self.names = names
        self.log, self.facts, self.intents = log, facts, intents
        self.profiles, self.live, self.deriver = profiles, live, deriver
        self.history_limit = history_limit
        # character portraits (harness/portrait.py): by portrait id, loaded by the engine for its
        # world; a profile names its portrait in `CharacterProfile.portrait`
        self.portraits: dict[str, Portrait] = {}
        # the rung each NPC starts on toward the player (a game package's person), by NPC id
        self.rung_seeds: dict[str, str] = {}
        self.relations = Relations(log, self.rung_seeds)

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
        if line:  # at the tail, not in the system message: the cached prefix stays identical
            msgs[-1] = {**msgs[-1], "content": msgs[-1]["content"] + "\n" + line}
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

    def corrections(self, character: str | None = None, *, narration: bool = False) -> list[str]:
        """The player's notes on model errors (stored per campaign), newest last: a line by
        `character` that the player marked as impossible, with the player's reason.
        `narration`: the notes on the narrator's passages instead (they never reach the NPCs)."""
        out = []
        for e in self.log.active([CORRECTION]):
            if bool(e.payload.get("narration")) != narration:
                continue
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
        # Order for prompt caching: what grows slowly first (the character's knowledge, condition),
        # the scene and what just happened last.
        parts: list[str] = []
        portrait, own_lines, leak = self._portrait_slice(character, scene)
        core = portrait or self.core_text(prof)  # a portrait replaces the core and the manner
        if core:
            parts.append(core)
        if portrait:  # the NPC's own standing toward the player (never the narrator's)
            rel = self.relations.get(character, PLAYER)
            parts.append(f"Your standing toward {self.ref(character, PLAYER)}: {rel.rung}, "
                         f"warmth {rel.warmth:g}, trust {rel.trust:g}.")
        if mem.knows:
            parts.append("What you know:\n" + "\n".join(self.knowledge_lines(mem)))
        if mem.state:
            parts.append("Your own condition:\n" + "\n".join(
                f"- {e.category}: {e.item}" for e in mem.state))
        parts.append(self._scene_header(scene, character))
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
        instruction = self.npc_instruction(prof)
        system = f"You are {prof.name}. {prof.description}".strip()
        if self.style is not None:
            system = self.style.npc_system(replace(prof, manner="") if portrait else prof)
            examples = self.style.npc_examples_section(" ".join([
                scene.location, prof.description, *(e.payload["text"] for e in seen[-2:]),
                *(it.fact.content for it in mem.knows[-4:])]))
            if examples:
                parts.append(examples)
        system += self.limits_section()
        known = (self.knowledge_lines(mem) + [self._seen(e, character) for e in seen]
                 + [f"- (own condition) {e.category}: {e.item}" for e in mem.state]
                 + [f"- (just noticed) {self.mask(character, f.content)}"
                    for _, f in mem.noticed])
        return NpcView(
            system=system, sections=parts,
            seen=[self._seen(e, character) for e in seen], instruction=instruction, known=known,
            name=prof.name, character=character, examples=own_lines, leak=leak or "",
            leak_scene=self.scene_key(character, scene) if leak else "",
            finish=lambda m, c=character, k=known_names: self.finish(m, c, k))

    # -- portraits ---------------------------------------------------------------------------
    def portrait_of(self, character: str) -> Portrait | None:
        prof = self.profiles.get(character)
        return self.portraits.get(prof.portrait) if prof is not None and prof.portrait else None

    def rung_of(self, character: str, toward: str = PLAYER) -> str:
        """The rung of the relationship ladder `character` stands on toward `toward`: the latest
        RELATION event; without one, toward the player the package seed (campaigns made before
        the store), else stranger; toward another NPC the portrait's static relations."""
        if toward == PLAYER:
            return self.relations.get(character, PLAYER).rung  # event, else the stored seed
        p = self.portrait_of(character)
        return p.relations.get(toward, "stranger") if p is not None else "stranger"

    def relation_line(self, npc: str, scene: Scene | None = None) -> str:
        """The NPC's standing toward the player for the omniscient judges (real names). With a
        scene and a portrait, the stance that standing selects."""
        rel = self.relations.get(npc, PLAYER)
        rung = rel.rung
        line = (f"{self.name(npc)} → the player: {rung}, warmth {rel.warmth:g}, "
                f"trust {rel.trust:g}")
        p = self.portrait_of(npc)
        if p is not None and scene is not None:
            line += f"; stance: {select_stance(p, rung, self.situation(npc, scene)).id}"
        return line

    def relation_lines(self, scene: Scene) -> list[str]:
        """One line per present NPC with a portrait (judges only)."""
        return [self.relation_line(c, scene) for c in scene.present
                if c != PLAYER and self.portrait_of(c) is not None]

    def situation(self, character: str, scene: Scene) -> Situation:
        """Power, audience and stakes for stance selection, in code. Audience: anyone present
        besides the NPC and the player. Stakes: mortal when this turn's judged outcome kills,
        high when an NPC acted against the player this turn or a weapon is out in the room, else
        low. Power: the NPC's own when its act toward the player this turn worked, else even."""
        audience = any(c not in (character, PLAYER) for c in scene.present)
        power, stakes = "even", "low"
        for e in reversed(self.log.active([OUTCOME_EVENT, UTTERANCE, ACTION])):
            if e.type != OUTCOME_EVENT:
                if (e.payload.get("speaker") or e.payload.get("actor")) == PLAYER:
                    break  # the player's input opens the turn: older outcomes are past
                continue
            p = e.payload
            if p.get("died"):
                stakes = "mortal"
            elif p.get("actor") not in (None, PLAYER) and stakes == "low":
                stakes = "high"
            if p.get("actor") == character and p.get("verdict") in ("works", "partly"):
                power = "self"
        if stakes == "low":
            snap = self.live.snapshot()
            if any(obs and DANGER.search(item)
                   for c in scene.present for (_, item), obs in snap.get(c, {}).items()):
                stakes = "high"
        return Situation(power, audience, stakes)

    def _portrait_slice(self, character: str, scene: Scene
                        ) -> tuple[str, tuple[str, ...], str | None]:
        """The slice text, the example lines shown (masked) and the leak it carries, if any."""
        p = self.portrait_of(character)
        if p is None:
            return "", (), None
        st = select_stance(p, self.rung_of(character), self.situation(character, scene))
        leak = self._leak_for(p, character, scene)
        text = self.portrait_text(p, st, character, leak)
        if leak and self.mask(character, leak) not in text:  # no room left in the slice
            leak = None
        # the copy check compares the reply with the example lines as the NPC saw them (masked)
        shown = tuple(m for m in (self.mask(character, x) for x in st.examples) if m in text)
        return text, shown, leak

    def scene_key(self, character: str, scene: Scene) -> str:
        return self.relations.scene_key(character, scene)

    def _leak_for(self, p: Portrait, character: str, scene: Scene) -> str | None:
        """A hidden-layer leak for this prompt: only with trust >= LEAK_TRUST and none used for
        this NPC in this scene yet (an active PORTRAIT_LEAK event, caused by the line that
        carried it); the portrait's leaks in turn."""
        if not p.leaks or self.relations.get(character, PLAYER).trust < LEAK_TRUST:
            return None
        key = self.scene_key(character, scene)
        used = [e for e in self.log.active([PORTRAIT_LEAK]) if e.payload.get("npc") == character]
        if any(e.payload.get("scene") == key for e in used):
            return None
        return p.leaks[len(used) % len(p.leaks)]

    def portrait_text(self, p: Portrait, stance: Stance, viewer: str,
                      leak: str | None = None) -> str:
        """Header plus slice, at most MAX_WORDS words in all, masked for `viewer`."""
        budget = MAX_WORDS - len(PORTRAIT_HEAD.split())
        while True:  # masking a name with an appearance can add words: shrink until it fits
            out = PORTRAIT_HEAD + "\n" + self.mask(viewer, slice_text(p, stance, leak, budget))
            over = len(out.split()) - MAX_WORDS
            if over <= 0 or budget <= 1:
                return out
            budget -= over

    def portrait_section(self, character: str, scene: Scene) -> str:
        """The portrait slice for this NPC's prompt (masked for the NPC); "" without a portrait."""
        return self._portrait_slice(character, scene)[0]

    def npc_instruction(self, prof: CharacterProfile, shape: Shape | None = None,
                        bounds: tuple[int, int] | None = None, beat: bool | None = None) -> str:
        """The closing instruction of an NPC call, with the response shape when one is given.
        `bounds` are the words the shape allows; the engine fits the reply to the same bounds.
        `beat` (with a style): this line carries one small action (True) or none (False)."""
        if self.style is not None:
            return self.style.npc_instruction(prof, self.language, shape, bounds, beat)
        lang = f" Speak in {self.language}." if self.language else ""
        if shape is Shape.GESTURE:
            return (shape_instruction(shape, None, name=prof.name) + " Write it as one short "
                    f"sentence in the third person about {prof.name}: no words spoken."
                    + (f" Write in {self.language}." if self.language else ""))
        return (f"Say what {prof.name} says next, aloud and in character. Write only {prof.name}'s "
                "own words as one continuous speech: no stage directions, no other characters' "
                "lines."
                + (" " + shape_instruction(shape, None, bounds=bounds, name=prof.name)
                   if shape is not None else "")
                + lang)

    @staticmethod
    def core_text(prof: CharacterProfile) -> str:
        """The immutable core of a profile (voice, drives, values), always verbatim (task 19)."""
        return ("Who you are (fixed, never changes): " + prof.core.strip()) if prof.core.strip() else ""

    def heard_line(self, viewer: str, speaker: str, text: str) -> str:
        return f"{self.ref(viewer, speaker)}: {text}"

    # -- narrator ----------------------------------------------------------------------------
    def narrator(self, scene: Scene, player_input: str, outcome: str | None = None) -> Messages:
        """The narrator speaks from the player character's perception (`PLAYER` below is the
        viewer): a person whose name the player character has not learned is only described, and
        a campaign fact that other people know but the player character does not (a rumour
        version, an authority's reaction, a plan made elsewhere) is not in the context (task 19).
        Layout for prompt caching: static rules (system), then what grows slowly (campaign
        state), then the scene and the player's input. `outcome`: the world's judgment of the
        player's attempt, decided before this prose (harness/outcome.py)."""
        campaign = [f for f in self.facts.all_campaign(scene.time) if self.player_can_know(f)]
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

        parts: list[str] = []
        if campaign:
            parts.append("Campaign state:\n" + "\n".join(f"- {m(f.content)}" for f in campaign))
        if canon:
            parts.append("Relevant canon:\n" + "\n".join(f"- {m(f.content)}" for f in canon))
        parts.append(self._scene_header(scene, PLAYER))
        state_lines = [
            f"- {self.ref(PLAYER, c)}: {cat}: {item} "
            f"({'observable' if items.is_observable(el, snap) else 'hidden'})"
            for c in scene.present
            for (cat, item), el in snap.get(c, {}).items()
        ]
        if state_lines:
            parts.append("Character state:\n" + "\n".join(state_lines))
        if recent:
            parts.append("Recent events:\n" + "\n".join(fmt(e) for e in recent))
        npcs = ", ".join(f"{c} ({self.ref(PLAYER, c)})" for c in scene.present if c != PLAYER)
        tail = f"The player does/says: {player_input}\n"
        notes = self.corrections(narration=True)
        if notes:
            tail += ("The player has pointed out mistakes in earlier narration; do not repeat "
                     "them:\n" + "\n".join(notes) + "\n")
        if outcome:
            tail += outcome + "\n"
        tail += "Narrate what happens next."
        if self.narration == "prose":
            # the full rules sit in the system message (cacheable); the one that models break most
            # often is repeated here, at the end, where it is read last
            tail += (" Plain prose only: no quotation marks and no dialogue dashes; nobody but "
                     "the player speaks in your text, NPC lines are written elsewhere.")
            rules = (
                "Write the narration as plain prose and nothing else: no JSON, no lists, no "
                "headings, no markup. Its length and shape follow the moment (a glance can be a "
                "sentence, a crisis several paragraphs); do not settle into a fixed pattern. "
                "Never write speech for anyone but the player: NPC lines are produced "
                "separately, so no quotation marks and no dialogue dashes; show what a "
                "character does, not what they say. Do not decide what the player character says, does or feels beyond "
                "what the player gave. "
                + PLAYER_CHARACTER_RULE + " Never narrate people, guards or events the player character "
                "could not perceive or has not been told of."
                + (" When someone else attacks, robs, restrains or arrests the player character, "
                   "narrate only the attempt and stop there: the world decides separately whether "
                   "it succeeds." if self.outcomes else "")
                + (f" Write in {self.language}." if self.language else "")
                + (f"\n{UNLIMITED_NARRATOR}" if self.player_unlimited else "")
                + self._intent_section())
            system = "You are the narrator of a role-playing game. Write vivid prose."
            if self.style is not None:
                system = self.style.narrator_system()
                examples = self.style.narrator_examples_section(" ".join([
                    scene.location, player_input, *(f.content for f in campaign[-3:])]))
                if examples:
                    parts.append(examples)
            return self.finish([
                {"role": "system", "content": system + "\n\n" + rules},
                {"role": "user", "content": "\n\n".join(parts + [tail])},
            ], PLAYER)
        tail += (
            "\n\nReply with ONE JSON object and nothing else:\n"
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
            {"role": "system", "content": system + self._intent_section()},
            {"role": "user", "content": "\n\n".join([*parts, tail])},
        ], PLAYER)

    def limits_section(self) -> str:
        """The campaign's content limits, for the NPCs and any other prose the player reads."""
        if not self.limits.strip():
            return ""
        return ("\n\nContent limits the player set for this campaign (never break them in what "
                "you write):\n" + self.limits.strip())

    def _intent_section(self) -> str:
        if not self.intent.strip():
            return ""
        return ("\n\nThe player's wishes for this campaign, set at its start. Follow them; they "
                "never override the rules above (they never let you write the player character's "
                "words, feelings or decisions):\n" + self.intent.strip())

    @staticmethod
    def player_can_know(f: Fact) -> bool:
        """A campaign fact reaches the narrator if the player character knows it, or nobody
        does (the narrator's own scenery); one that only other people know stays out."""
        return not f.knowers or any(k.character == PLAYER for k in f.knowers)

    # -- director ----------------------------------------------------------------------------
    def director_state(self, scene: Scene, player_input: str, narration: str) -> list[str]:
        """What the speaker decider sees: the scene, the latest exchange, the narration."""
        recent = self.log.recent_dialogue(limit=4)
        lines = [self._scene_header(scene)]
        if recent:
            lines.append("Recent:\n" + "\n".join(self._seen(e) for e in recent))
        lines.append(f"The player does/says: {player_input}")
        if narration:  # none when the moment is just talk (living dialogue)
            lines.append(f"Narration: {narration}")
        rel = self.relation_lines(scene)
        if rel:
            lines.append("Relationships:\n" + "\n".join(rel))
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
    def extractor(self, scene: Scene, segments: list[tuple[str, str]],
                  outcomes: Sequence[str] = ()) -> Messages:
        """segments: (source key, text). Asks for a JSON diff: fact text + source + notability,
        and live-state changes. Knowers are not asked for: code computes perception."""
        who = ", ".join(scene.present + scene.outside)
        names = [self.describe(c) for c in scene.present + scene.outside]
        keys = ", ".join(k for k, _ in segments)
        body = "\n".join(f"[{k}] {t}" for k, t in segments)
        snap = self.live.snapshot()
        cur = [
            f"- {c}: {cat}: {item}"
            + (f" [id: {el.id}]" if self.item_ids and el.id else "")
            + (f" [location: {el.location}]" if self.item_ids and el.location else "")
            + (" [container, open]" if self.item_ids and el.open else "")
            + f" ({'observable' if items.is_observable(el, snap) else 'hidden'})"
            for c, elems in snap.items()
            for (cat, item), el in elems.items()
        ]
        hidden = self.names and any(self.names.hidden(c) for c in scene.present + scene.outside)
        instr = (
            "Extract new facts and live-state changes from the passages below as JSON, "
            "nothing else:\n"
            '{"new_facts": [{"content": str, "source": <one of: ' + keys + '>, '
            '"notability": number 0..1, "location": optional str}],\n'
            ' "state_changes": [{"character": <id>, "category": "injury"|"clothing"|"inventory"|'
            '"equipment"|"internal"|"appearance", "op": "add"|"remove"|"reveal"|"hide"'
            + ('|"move"|"realize"' if self.item_ids else "") + ', "item": str, '
            '"observable": true|false, "source": <segment>'
            + (', "id": optional existing item id, "location": optional str' if self.item_ids else "")
            + '}]}\n'
            f"Characters: {who}. Do not say who knows or saw a fact; that is decided elsewhere. "
            '"remove" only works on an item the character currently has; "reveal"/"hide" change '
            "whether an existing item is observable. "
            + ('Items listed with an [id: ...] are referred to by that "id" for "remove", "move", '
               '"reveal", "hide" and "realize" (never invent ids; a new item is added by its text '
               'and gets its id elsewhere). "move" needs a "location": "worn", "in_hand", '
               '"on:<place>" or "in:<container id>"; "add" may give one too. "realize" is for a '
               'character who learns of an item they carried unaware. ' if self.item_ids else "")
            + "Do not emit any other keys. Figures of speech and "
            "gestures are not state (\'took his hand\' adds no hand to anyone's inventory).\n"
            + (f"Names (a passage may describe a person without naming them; in facts, use the "
               f"name): {'; '.join(names)}.\n" if hidden else "")
            + (f"Write every fact's content and every state item in {self.record_language}"
               + ("; names, places and titles stay in Ukrainian as they are written. "
                  if self.glossary else ". ") if self.record_language else "")
            + (UNLIMITED_EXTRACTOR + "\n" if self.player_unlimited else "")
            + ("\n".join(outcomes) + "\nRecord what really happened (a failed attempt did not "
               "succeed; its consequences are facts and state changes), not what was hoped.\n"
               if outcomes else "")
            + "Current state:\n" + ("\n".join(cur) if cur else "- (none)")
        )
        return self.finish([
            {"role": "system", "content": "You are a precise fact extractor."},
            {"role": "user", "content": instr + "\n\n" + body},
        ])
