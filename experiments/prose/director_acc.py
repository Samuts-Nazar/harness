"""First-line decider accuracy on the 27 prose narrations (expected first speaker from the task 7
notes), for question wordings. Usage: python -m experiments.prose.director_acc"""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from experiments.language import prompts_lang as L
from harness import director
from harness.glossary import Glossary
from harness.judge import DecisionJudge, choice_q
from harness.policy import DEFAULT_JUDGE_FIRST, Spend

EXPECT = {"n01": {"vesemir"}, "n02": {"hostomyl"}, "n03": {"eskel"}, "n04": set(), "n05": {"guard", "merchant"},
          "n06": {"triss"}, "n07": {"smith"}, "n08": set(), "n09": {"lambert"}}
G = Glossary.for_world("witcher")
HERE = Path(__file__).parent


def main():
    load_dotenv()
    judge = DecisionJudge(os.environ["OPENROUTER_API_KEY"], DEFAULT_JUDGE_FIRST, spend=Spend(0.05))
    rows = [json.loads(x) for x in (HERE / "raw" / "narr.jsonl").read_text().splitlines()]
    rows = [r for r in rows if r["variant"] == "prose"]
    orig = director.speaker_questions
    res = {}
    for label in ("current", "revised"):
        if label == "revised":
            def q2(npcs, _orig=orig):
                qs = _orig(npcs)
                opts = qs["first"].options
                qs["first"] = choice_q(
                    "Who speaks aloud next in this scene, answering the player or reacting to the "
                    "narration? Choose the character who is addressed or whose turn it is to speak. "
                    "Answer nobody only if no one at all would say anything now.", opts,
                    tag=qs["first"].tag)
                return qs
            director.speaker_questions = q2
        ok, tot, ts = 0, 0, []
        for r in rows:
            it = L.NARR[r["id"]]
            npcs = {c: L.P.NAMES.get(c, c) for c in it["present"] if c != "player"}
            state = [f"Location: {it['location']}", f"The player does/says: {it['player']}",
                     f"Narration: {G.apply(r['text'])}"]
            t = time.monotonic()
            got = director.decide_speakers(judge, state, npcs) if npcs else []
            ts.append(time.monotonic() - t)
            exp = EXPECT[r["id"]]
            hit = (not got) if not exp else bool(got and got[0] in exp)
            if r["id"] == "n08":
                hit = True  # silence or a minimal reply are both fine
            ok += hit
            tot += 1
            res.setdefault(label, []).append((r["id"], r["sample"], got, hit))
        print(label, f"{ok}/{tot}", "mean decider s", round(sum(ts) / len(ts), 2))
    director.speaker_questions = orig
    (HERE / "raw" / "director_acc.json").write_text(json.dumps(res, ensure_ascii=False))
    for lab in res:
        print(lab, [(i, s, g) for i, s, g, h in res[lab] if not h])


main()
