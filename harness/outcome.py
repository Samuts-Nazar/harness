"""Outcome before prose (task 19, pending decisions 14).

The player decides what the character does and attempts. The world judges per situation whether it
works, BEFORE any prose is written: no dice, no stats, one batched typed judgment (the decider
first, the LLM escalation per the usual rule) that may say "works", "partly" or "fails", with a
reason from a closed list. The result is stored as an `outcome` event; the narrator is told it and
only narrates it. Real failure has consequences in the world state (the extractor is told what
really happened). Death of the player character ends the campaign (`character_death` event,
read-only afterwards, a chronicle screen in the app).

`player_unbounded` (the Vizima pilot demon): the player's own acts always happen; only reactions
are judged. NPC acts toward the player (attack, theft, arrest) are judged the same way, one step
later in the turn (`npc_acts`), because the NPC actions come from the scene director.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence

from .judge import JudgeError, choice_q, yes_no_q
from .models import PLAYER, Event

if TYPE_CHECKING:  # pragma: no cover
    from .pipeline import Engine

OUTCOME = "outcome"
CHARACTER_DEATH = "character_death"

WORKS, PARTLY, FAILS = "works", "partly", "fails"
VERDICTS = {
    WORKS: "it works as the attempt intended",
    PARTLY: "it works only in part, or at a cost, or not as intended",
    FAILS: "it does not work; something real follows from the failure",
}
REASONS = {  # closed list: the judge cannot write text
    "none": "nothing stands in the way",
    "beyond_ability": "beyond what this person can do",
    "lacks_means": "lacks the tools, strength or time needed",
    "opposed": "someone present opposes it and can stop it",
    "noticed": "it is noticed or interrupted before it is done",
    "circumstance": "the place, weather, crowd or timing prevents it",
    "body": "the character's body (wound, fatigue, drink, poison) prevents it",
    "not_possible": "the world does not allow it at all",
}
REASON_TEXT = {
    "none": "", "beyond_ability": "it was beyond what the character can do",
    "lacks_means": "the character lacked the means", "opposed": "someone present stopped it",
    "noticed": "it was noticed or interrupted", "circumstance": "the circumstances prevented it",
    "body": "the character's body did not allow it",
    "not_possible": "the world does not allow this",
}


class CampaignEnded(RuntimeError):
    """The player character is dead: the campaign is read-only."""


@dataclass(frozen=True)
class Outcome:
    verdict: str
    reason: str = "none"
    died: bool = False
    actor: str = PLAYER
    text: str = ""   # what was attempted
    unbounded: bool = False
    event_id: int | None = None

    def for_narrator(self) -> str:
        """The line the narrator and the extractor get; it states what really happened."""
        if self.actor == PLAYER:
            head = "The world has judged the player character's attempt BEFORE you write: "
        else:
            head = f"The world has judged an act toward the player character ({self.text}): "
        why = REASON_TEXT.get(self.reason, "")
        body = {WORKS: "it works.", PARTLY: "it works only in part or at a cost.",
                FAILS: "it fails."}[self.verdict]
        if self.unbounded:
            body = "it happens exactly as declared (the character has no limits)."
        extra = " The character dies; narrate the death and nothing after it." if self.died else ""
        return (head + body + (f" Reason: {why}." if why and self.verdict != WORKS else "")
                + " Narrate exactly this outcome; do not turn a failure into a success or the "
                "other way round. A failure has real consequences in the world (a wound, a lost "
                "or broken thing, being noticed)." + extra)


def _state_lines(eng: "Engine") -> list[str]:
    snap = eng.live.snapshot()
    lines = []
    for cid in eng.scene.present:
        for (cat, item), obs in snap.get(cid, {}).items():
            lines.append(f"- {eng.ctx.name(cid)}: {cat}: {item}")
    return lines


class OutcomeJudge:
    """Judgments about outcomes. One batched `Judge.ask` per player attempt."""

    def __init__(self, eng: "Engine") -> None:
        self.eng = eng

    def _context(self, extra: Sequence[str] = ()) -> list[str]:
        eng, sc = self.eng, self.eng.scene
        prof = eng.profiles.get(PLAYER)
        recent = eng.log.recent_dialogue(limit=4, include_narration=True)
        lines = [eng._scene_header_omniscient(),
                 f"The player character: {prof.description if prof else ''}"]
        st = _state_lines(eng)
        if st:
            lines.append("Character states:\n" + "\n".join(st))
        if recent:
            lines.append("Recent:\n" + "\n".join(
                eng.ctx._seen(e) if e.type != "narration" else f"[narration] {e.payload['text']}"
                for e in recent))
        rel = eng.ctx.relation_lines(sc)
        if rel:
            lines.append("Relationships:\n" + "\n".join(rel))
        lines.extend(extra)
        return lines

    # -- the player's attempt --------------------------------------------------------------
    def player(self, text: str, *, unbounded: bool) -> Outcome | None:
        """None: not an attempt that can fail (speech, looking, waiting)."""
        eng = self.eng
        if unbounded:
            return Outcome(WORKS, "none", actor=PLAYER, text=text, unbounded=True)
        qs = {
            "attempt": yes_no_q(
                "Does the player's input contain something the character tries to DO to the world "
                "or to other people that could fail or be stopped (a fight, a theft, a climb, a "
                "lie that must be believed is NOT this; ordinary speech, looking, waiting, "
                "walking in a safe place are not)?", tag="outcome_attempt"),
            "verdict": choice_q(
                "Judge the attempt in this situation, as the world would, with no dice: what the "
                "character is, has, and where they are. It may be impossible.",
                VERDICTS, tag="outcome_verdict"),
            "reason": choice_q("If it does not fully work, what is the main reason?", REASONS,
                               tag="outcome_reason"),
            "death": yes_no_q(
                "If it does not fully work, does the result kill the player character right "
                "now?", tag="character_death"),
        }
        try:
            got = eng.judge.ask(self._context([f"The player's input: {text}"]), qs)
        except JudgeError as e:
            eng._note("outcome_unavailable", error=str(e))
            return None
        if not got["attempt"].answer:
            return None
        verdict = str(got["verdict"].answer)
        verdict = verdict if verdict in VERDICTS else WORKS
        reason = str(got["reason"].answer) if verdict != WORKS else "none"
        died = bool(got["death"].answer) and verdict != WORKS
        return Outcome(verdict, reason if reason in REASONS else "circumstance", died,
                       PLAYER, text)

    # -- acts toward the player --------------------------------------------------------------
    def npc_acts(self, acts: Sequence[tuple[str, str]], *, unbounded: bool) -> list[Outcome]:
        """`acts`: (actor, observable action text). Those that are attacks, thefts, arrests or
        other attempts against the player character get an outcome."""
        eng = self.eng
        if not acts:
            return []
        qs = {f"hostile:{i}": yes_no_q(
            f"Is this an attempt by someone else against the player character's body, "
            f"belongings or freedom (an attack, a theft, an arrest, restraining, poisoning)?"
            f" Act: {a}", tag="npc_act_against_player") for i, (_, a) in enumerate(acts)}
        try:
            got = eng.judge.ask(self._context(), qs)
        except JudgeError as e:
            eng._note("outcome_unavailable", error=str(e))
            return []
        hostile = [i for i in range(len(acts)) if got[f"hostile:{i}"].answer]
        out: list[Outcome] = []
        for i in hostile:
            actor, text = acts[i]
            who = eng.ctx.name(actor) if actor in eng.profiles else actor
            lim = ("The player character is a being without limits."
                   if unbounded else "")
            qs2 = {
                "verdict": choice_q(
                    "Does this act against the player character succeed? 'works' = it fully "
                    "succeeds, 'fails' = the player character is not affected.", VERDICTS,
                    tag="outcome_verdict"),
                "reason": choice_q("What decides it?", REASONS, tag="outcome_reason"),
                "death": yes_no_q("If it succeeds, does it kill the player character?",
                                  tag="character_death"),
            }
            try:
                g2 = eng.judge.ask(self._context([f"The act ({who}): {text}", lim]), qs2)
            except JudgeError as e:
                eng._note("outcome_unavailable", error=str(e))
                continue
            verdict = str(g2["verdict"].answer)
            verdict = verdict if verdict in VERDICTS else FAILS
            reason = str(g2["reason"].answer)
            died = bool(g2["death"].answer) and verdict != FAILS
            out.append(Outcome(verdict, reason if reason in REASONS else "circumstance", died,
                               actor, f"{who}: {text}"))
        return out


def record_outcome(eng: "Engine", o: Outcome, cause: Event | None) -> tuple[Outcome, Event]:
    """Store the outcome (and a death) as events; a rollback of the cause removes them."""
    ev = eng._event(OUTCOME, [PLAYER] + ([o.actor] if o.actor in eng.profiles and o.actor != PLAYER else []),
                    {"text": o.text, "verdict": o.verdict, "reason": o.reason,
                     "reason_text": REASON_TEXT.get(o.reason, ""), "died": o.died,
                     "actor": o.actor, "unbounded": o.unbounded},
                    notability=0.3, cause_id=cause.id if cause else None)
    return Outcome(o.verdict, o.reason, o.died, o.actor, o.text, o.unbounded, ev.id), ev


def record_death(eng: "Engine", o: Outcome, cause: Event) -> Event:
    return eng._event(CHARACTER_DEATH, [PLAYER],
                      {"text": f"The player character dies: {o.text}", "reason": o.reason,
                       "outcome_event": o.event_id}, notability=1.0, cause_id=cause.id)


def chronicle(eng: "Engine") -> list[dict[str, Any]]:
    """The final chronicle: what the player character knew and did, in order, to the death."""
    from .models import NARRATION, UTTERANCE
    lines: list[dict[str, Any]] = []
    death: dict[str, Any] | None = None
    for e in eng.log.active([NARRATION, UTTERANCE, OUTCOME, CHARACTER_DEATH]):
        if e.type == NARRATION:
            lines.append({"kind": "narr", "text": e.payload["text"], "t": e.game_time})
        elif e.type == UTTERANCE:
            who = eng.ctx.label(PLAYER, e.payload["speaker"], e.id)
            lines.append({"kind": "line", "who": who, "text": e.payload["text"], "t": e.game_time})
        elif e.type == OUTCOME and e.payload.get("verdict") != WORKS:
            lines.append({"kind": "outcome", "text": e.payload["text"],
                          "verdict": e.payload["verdict"], "t": e.game_time})
        elif e.type == CHARACTER_DEATH:  # written before the death is narrated: shown last
            death = {"kind": "death", "text": e.payload["text"], "t": e.game_time}
    if death:
        lines.append(death)
    return lines
