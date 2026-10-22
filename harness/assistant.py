"""Turn assistant: a few short action lines in the player's voice, from what the player
character knows and nothing else.

The context is built from the player character's own view (their derived memory, the scene as
they perceive it, what they witnessed; names they do not know stay masked), the same filter the
panel and the narrator use. Building it reads the database, so it is a separate step
(`context`) from the model call (`ask`): a caller on a thread that must not touch the database
builds the context first, on a thread that may, and calls `ask` anywhere. Drafts are not part of
the log: nothing here writes to the engine's records.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from .models import PLAYER
from .providers import ProviderError
from .style import cut_foreign, foreign_runs

if TYPE_CHECKING:
    from .pipeline import Engine

ROLE = "assistant"
SEEN_LIMIT = 8
LINE_MAX = 220

SYSTEM = (
    "You are the turn assistant of a text role-playing game. You suggest what the player's "
    "character could do or say next. You know only what the player's character knows, given "
    "below; never use anything else. "
    "Rules: suggest only the character's own deliberate actions and words. Never feelings, "
    "thoughts or inner states (not \"*відчуває страх*\"): only the player decides what the "
    "character feels. Never outcomes or other characters' reactions (not \"*вбиває Горста*\", "
    "not \"він погоджується\"): the world decides results. Write the attempt, not its result. "
    "Write {n} different options, each one short (at most about 20 words), in Ukrainian, in the "
    "first person as the character, one per line, no numbering and no comments. "
    "An action is written between asterisks, like *дістає меч*; speech is written plainly, "
    "without quotes. Offer a mix: not all options of one kind. Options must fit the situation "
    "and the character, and differ in intent."
)


@dataclass(frozen=True)
class Context:
    """The player character's view, rendered. Plain text: safe to keep and use from any thread.
    `known`: the ids whose names the player character knew when it was rendered (the suggestions
    are masked with it, so `ask` never reads the database)."""
    system: str
    user: str
    known: frozenset[str] | None = None


def context(engine: "Engine") -> Context:
    """Render the player character's view. Reads the database: call it only on a thread that may."""
    ctx, scene = engine.ctx, engine.scene
    mem = engine.deriver.derive(PLAYER, scene.time)
    prof = engine.profiles.get(PLAYER)
    parts: list[str] = []
    if prof is not None:
        core = ctx.core_text(prof)
        who = f"You play {prof.name}. {prof.description}".strip()
        parts.append(who + ("\n" + core if core else ""))
    if mem.knows:
        parts.append("What the character knows:\n" + "\n".join(ctx.knowledge_lines(mem)))
    if mem.state:
        parts.append("The character's own condition:\n" + "\n".join(
            f"- {e.category}: {e.item}" for e in mem.state))
    parts.append(ctx._scene_header(scene, PLAYER))
    if mem.noticed:
        parts.append("The character has just noticed:\n" + "\n".join(
            f"- {ctx.mask(PLAYER, f.content)}" for _, f in mem.noticed))
    seen = engine.log.recent_dialogue(witnessed_by=PLAYER, limit=SEEN_LIMIT)
    if seen:
        parts.append("What just happened (as the character perceived it):\n"
                     + "\n".join(ctx._seen(e, PLAYER) for e in seen))
    known = engine.names.known_set(PLAYER) if engine.names else None
    msgs = ctx.finish([{"role": "system", "content": SYSTEM + ctx.limits_section()},
                       {"role": "user", "content": "\n\n".join(parts)}], PLAYER, known)
    return Context(msgs[0]["content"], msgs[1]["content"], known)   # None = no name tracking, no masking


def parse(raw: str, n: int, avoid: Sequence[str] = ()) -> list[str]:
    """One option per line; bullets, numbers and quotes dropped; duplicates and avoided ones out."""
    skip = {a.strip().lower() for a in avoid}
    out: list[str] = []
    for line in raw.splitlines():
        s = re.sub(r"^\s*(?:[-–—•*]\s+|\d+[.)]\s+)", "", line).strip().strip('"«»“”').strip()
        if not s or len(s) > LINE_MAX or s.lower() in skip or s in out:
            continue
        out.append(s)
        if len(out) == n:
            break
    return out


def ask(engine: "Engine", ctx: Context, n: int = 3, avoid: Sequence[str] = ()) -> list[str]:
    """The model call on an already rendered context (no database access)."""
    user = ctx.user
    if avoid:
        user += "\n\nAlready offered (give different ones):\n" + "\n".join(f"- {a}" for a in avoid)
    user += f"\n\nWrite {n} options now."
    messages = [{"role": "system", "content": ctx.system.replace("{n}", str(n))},
                {"role": "user", "content": user}]
    # Not Engine._complete: that counts into the turn's shared llm_calls/devlog, and this runs on
    # a thread that may overlap the next turn. Assistant calls are counted on their own.
    models = engine.models
    lang = getattr(engine, "output_language", None)

    def call() -> str:
        engine.assistant_calls.append(ROLE)
        try:
            return engine.provider.complete(models.assistant, messages)
        except ProviderError:
            fallback = models.assistant_fallback
            if not fallback:
                raise
            engine.assistant_calls.append(ROLE)
            return engine.provider.complete(fallback, messages)

    raw = call()
    if foreign_runs(raw, lang):  # the engine's script-switch check: once more, then cut
        raw = call()
        if foreign_runs(raw, lang):
            raw = "\n".join(cut_foreign(line, lang) for line in raw.splitlines())
    out = parse(raw, n, avoid)
    if ctx.known is not None:  # a name the character has not learned stays an appearance
        masked = [engine.ctx.mask(PLAYER, s, ctx.known) for s in out]
        out = []
        for s in masked:
            if s not in out and s.strip().lower() not in {a.strip().lower() for a in avoid}:
                out.append(s)
    return out


def suggest(engine: "Engine", n: int = 3, avoid: Sequence[str] = ()) -> list[str]:
    """Up to `n` short action lines in the player's voice (`*…*` marks actions)."""
    return ask(engine, context(engine), n, avoid)
