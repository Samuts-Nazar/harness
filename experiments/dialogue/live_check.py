"""Live check of the living dialogue (task LD-8): real models, the three reference scenes
(worlds/witcher/scenes/*.json) and two 20-turn inn sessions, each in `living` and `classic` mode.

    python -m experiments.dialogue.live_check run scene:rinde_council      # one unit
    python -m experiments.dialogue.live_check run session:A:living
    python -m experiments.dialogue.live_check run all
    python -m experiments.dialogue.live_check report                       # aggregate saved units

Units are saved as JSON under /home/cock/projects/harness/campaigns/ld/ (git-ignored), with a
cassette of every provider call (`cassette.jsonl`: model, messages, output). Nothing there is
committed. The key is read from the .env by absolute path and never printed.

Scenes: the player is a silent onlooker and every cast member is an engine speaker, the book
protagonist included, so the book numbers of the scene (all its dialogue lines) are like for like.
Book numbers are computed on the fly from the local book file and only numbers are kept.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ABS = Path("/home/cock/projects/harness")
OUT = ABS / "campaigns" / "ld"
BOOK = ABS / "data" / "witcher_books.txt"
SCENES = REPO / "worlds" / "witcher" / "scenes"
SPEND_CAP = 0.58

SESSIONS = {
    "A": [
        "Сідайте. Я слухаю вас.",
        "Скільки ви готові заплатити?",
        "Що саме виє на млині?",
        "Ельзо, це ваш млин?",
        "Хто загинув?",
        "Гм.",
        "Хто з вас каже правду?",
        "Мені потрібен аванс.",
        "Горсте, ви мені не довіряєте?",
        "Добре.",
        "Скільки людей знає про це?",
        "Коли воно вперше з'явилося?",
        "Ельзо, що ви приховуєте?",
        "Я мовчу й дивлюся на обох по черзі.",
        "Мені потрібні срібло й пастки.",
        "Хто піде зі мною?",
        "Не поспішайте обоє.",
        "Домовились. Я виходжу на світанку.",
        "Дякую за вечерю.",
        "Це все. Більше питань нема.",
    ],
    "B": [
        "Доброго вечора. Тут вільно?",
        "Горсте, давайте без церемоній. Що за халепа?",
        "Я не взявся за справу. Поки що.",
        "Ельзо, а ви що тут робите?",
        "Мене це не лякає.",
        "Он як.",
        "Скільки коштує ніч у вас, і чи є що поїсти?",
        "Горсте, ви брешете. Я бачу.",
        "Ельзо, скажіть щось.",
        "Дай-но подумаю.",
        "Хтось із села бачив цю тварюку на власні очі?",
        "Я кладу долоню на руків'я меча й чекаю.",
        "А якщо я відмовлюсь?",
        "Ні.",
        "Горсте, ти мене розсмішив.",
        "Ельзо, ти йому віриш?",
        "Гаразд, гаразд. Хай буде по-вашому, але з однією умовою.",
        "Пів суми наперед, решту при мені в млині.",
        "То що, згода?",
        "Я підводжуся з-за столу.",
    ],
}

AB_TURNS = 10  # session A's first turns, in both modes, are the A/B pairs


class Cassette:
    """Wraps a provider: appends every call (model, messages, output, seconds) to a jsonl file."""

    def __init__(self, inner, path: Path) -> None:
        self.inner, self.path, self._lock = inner, path, threading.Lock()

    @property
    def parallel_ok(self) -> bool:
        return bool(getattr(self.inner, "parallel_ok", False))

    def complete(self, model, messages):
        t0, out = time.monotonic(), ""
        try:
            out = self.inner.complete(model, messages)
            return out
        finally:
            rec = {"model": model, "messages": messages, "out": out,
                   "seconds": round(time.monotonic() - t0, 2)}
            with self._lock, self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def stream(self, model, messages):
        yield from self.inner.stream(model, messages)


def make_stack():
    from dotenv import load_dotenv
    load_dotenv(ABS / ".env")
    from app.stacks import live_stack
    stack = live_stack(SPEND_CAP)
    OUT.mkdir(parents=True, exist_ok=True)
    stack.provider = Cassette(stack.provider, OUT / f"cassette-{os.getpid()}.jsonl")
    return stack


def run_turns(eng, texts, spend, label):
    """Run the scripted player turns; returns the turn records."""
    recs = []
    for i, text in enumerate(texts, 1):
        t0 = time.monotonic()
        first: list[float] = []
        cost0 = spend.total
        res = eng.turn(text, defer_slow=True,
                       on_word=lambda s, w, f=first, t=t0: f.append(time.monotonic() - t) if not f else None)
        fast = time.monotonic() - t0
        eng.settle()
        d = res.decisions
        recs.append({
            "n": i, "player": text, "narration": res.narration,
            "exchange": [list(x) for x in res.exchange],
            "utterances": [[u.payload["speaker"], u.payload["text"]] for u in res.utterances],
            "stop_reason": res.stop_reason,
            "first_word_s": round(first[0], 2) if first else None,
            "fast_s": round(fast, 2),
            "decisions": d.as_dict() if d else None,
            "cost": round(spend.total - cost0, 5)})
        print(f"[{label}] turn {i}: {len(res.utterances)} lines, first word "
              f"{recs[-1]['first_word_s']}s, spend {spend.total:.4f}", flush=True)
    return recs


def run_scene(sid: str, stack):
    from app.campaigns import Recorder
    from harness.glossary import Glossary
    from harness.models import PLAYER, CharacterProfile, Scene
    from harness.pipeline import Engine
    from harness.profile import load_profile
    from harness.style import Style
    spec = json.loads((SCENES / f"{sid}.json").read_text(encoding="utf-8"))
    rec = Recorder(stack.provider, stack.models, stack.spend)
    profiles = [CharacterProfile(PLAYER, "Гість", spec["onlooker"], appearance="мовчазний сторонній")]
    profiles += [CharacterProfile(c["id"], c["name"], c["description"], appearance=c.get("appearance", ""))
                 for c in spec["cast"]]
    ids = [c["id"] for c in spec["cast"]]
    eng = Engine(rec, profiles, Scene(spec["location"], (), time=0),
                 models=stack.models, judge=stack.judge, glossary=Glossary.for_world("witcher"),
                 style=Style.load("witcher"), dialogue="living", world_profile=load_profile("witcher"))
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            eng.acquaint(a, b)
    for c in ids:
        eng.enter_scene(c)
    eng.enter_scene(PLAYER)
    cost0 = stack.spend.total
    recs = run_turns(eng, spec["turns"], stack.spend, f"scene:{sid}")
    return eng, rec, {"unit": f"scene:{sid}", "mode": "living", "setup": spec["setup"],
                      "book": spec["book"], "turns": recs, "cost": round(stack.spend.total - cost0, 5)}


def run_session(name: str, mode: str, stack):
    from app import campaigns
    campaigns.DIALOGUE = mode
    cost0 = stack.spend.total
    camp = campaigns.open_campaign(stack, root=OUT / "camps", new=True, name=f"ld-{name}-{mode}-{int(time.time())}",
                                   data_file=OUT / "no-character-file.md")
    eng = camp.engine
    recs = run_turns(eng, SESSIONS[name], stack.spend, f"session:{name}:{mode}")
    return eng, camp.recorder, {"unit": f"session:{name}:{mode}", "mode": mode, "turns": recs,
                                "cost": round(stack.spend.total - cost0, 5)}


def finish(eng, rec, out: dict) -> dict:
    from harness.profile import profile_of_lines
    out["lines"] = list(eng.session_lines)
    out["dialogue_report"] = eng.dialogue_report()
    out["calls"] = rec.calls
    out["devlog_kinds"] = [n["kind"] for n in eng.devlog]
    out["slow_failures"] = [n for n in eng.devlog if n["kind"] == "slow_lane_failed"]
    out["slow_failure"] = repr(eng.slow_failure) if eng.slow_failure else None
    path = OUT / (out["unit"].replace(":", "_") + ".json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {path}  cost {out['cost']}", flush=True)
    return out


def run_unit(unit: str, stack) -> None:
    kind, *rest = unit.split(":")
    if kind == "scene":
        eng, rec, out = run_scene(rest[0], stack)
    else:
        eng, rec, out = run_session(rest[0], rest[1], stack)
    finish(eng, rec, out)
    eng.close()


# ---------------------------------------------------------------------------------------------
def book_numbers(a: int, b: int) -> dict:
    from harness.profile import _core, dialogue_lines
    text = "\n".join(BOOK.read_text(encoding="utf-8").splitlines()[a - 1:b])
    core = _core(dialogue_lines(text))
    return {"n_lines": core["n_lines"], "median": core["median_words"],
            "share_1_3": core["length_bins"]["1"] + core["length_bins"]["2-3"],
            "question_share": core["question_share"], "no_beat_share": core["no_beat_share"]}


def unit_numbers(d: dict, prof) -> dict:
    from harness.profile import distance, profile_of_lines
    lines = d["lines"]
    p = profile_of_lines(lines)
    words = [len(x.split()) for x in lines]
    first = [t["first_word_s"] for t in d["turns"] if t["first_word_s"] is not None]
    fast = [t["fast_s"] for t in d["turns"]]
    roles: dict[str, int] = {}
    tot = dict(judgments=0, escalations=0, code_choices=0, total=0)
    for t in d["turns"]:
        dc = t["decisions"] or {}
        for k in tot:
            tot[k] += dc.get(k, 0)
        for r, n in (dc.get("llm_calls_by_role") or {}).items():
            roles[r.split(":")[0]] = roles.get(r.split(":")[0], 0) + n
    return {"unit": d["unit"], "n_lines": p.n_lines, "median": p.median_words,
            "share_1_3": p.length_bins["1"] + p.length_bins["2-3"],
            "ratio_to_profile_median": p.median_words / prof.median_words,
            "question_share": p.question_share, "no_beat_share": p.no_beat_share,
            "length_bins": p.length_bins,
            "distance": distance(p, prof, speech_only=True),
            "first_word_median_s": statistics.median(first) if first else None,
            "first_word_max_s": max(first) if first else None,
            "turn_fast_median_s": statistics.median(fast), "turn_fast_max_s": max(fast),
            "lines_per_turn": len(lines) / len(d["turns"]), "cost": d["cost"],
            "decisions_session": {**tot, "by_role": roles},
            "stop_reasons": {r: sum(1 for t in d["turns"] if t["stop_reason"] == r)
                             for r in {t["stop_reason"] for t in d["turns"]}},
            "narration_turns": sum(1 for t in d["turns"] if t["narration"])}


def report() -> None:
    from harness.profile import load_profile
    prof = load_profile("witcher")
    rows = []
    for f in sorted(OUT.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if "unit" not in d:
            continue
        r = unit_numbers(d, prof)
        if d.get("book"):
            r["book_scene"] = book_numbers(*d["book"]["lines"])
        rows.append(r)
    (OUT / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"profile: median {prof.median_words}, share 1-3 words "
          f"{prof.length_bins['1'] + prof.length_bins['2-3']:.3f}")
    for r in rows:
        print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()
                          if k not in ("length_bins", "distance")}, ensure_ascii=False))


def decision_tables() -> str:
    """Markdown tables of decision counts: per action (one player turn), scene and session."""
    units = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(OUT.glob("*.json"))
             if f.name != "results.json"]
    out = ["| unit | turns | judgments | of them escalated | model calls (narrator/npc/extractor/other) "
           "| code choices | total | per turn: mean / min / max |", "|---|---|---|---|---|---|---|---|"]
    for d in units:
        per = [(t["decisions"] or {}).get("total", 0) for t in d["turns"]]
        roles: dict[str, int] = {}
        j = e = c = 0
        for t in d["turns"]:
            dc = t["decisions"] or {}
            j, e, c = j + dc.get("judgments", 0), e + dc.get("escalations", 0), c + dc.get("code_choices", 0)
            for r, n in (dc.get("llm_calls_by_role") or {}).items():
                k = r.split(":")[0]
                k = k if k in ("narrator", "npc", "extractor") else "other"
                roles[k] = roles.get(k, 0) + n
        rs = "/".join(str(roles.get(k, 0)) for k in ("narrator", "npc", "extractor", "other"))
        out.append(f"| {d['unit']} | {len(per)} | {j} | {e} | {rs} | {c} | {sum(per)} | "
                   f"{sum(per) / len(per):.1f} / {min(per)} / {max(per)} |")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if argv[:1] == ["report"]:
        report()
        return 0
    if argv[:1] == ["decisions"]:
        print(decision_tables())
        return 0
    if argv[:1] != ["run"] or len(argv) < 2:
        print(__doc__)
        return 2
    units = argv[1:]
    if units == ["all"]:
        units = [f"scene:{p.stem}" for p in sorted(SCENES.glob("*.json"))] + [
            f"session:{n}:{m}" for n in SESSIONS for m in ("living", "classic")]
    stack = make_stack()
    for u in units:
        run_unit(u, stack)
    print(f"spend USD: {stack.spend.total:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
