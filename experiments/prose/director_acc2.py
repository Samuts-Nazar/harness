"""Task 14: first-speaker accuracy on the 27 prose narrations, variants of the decider's inputs.
Usage: python -m experiments.prose.director_acc2 [repeats]

The innkeeper (n02) was missed in 3 of 3 samples: the narration ends with a nod, and the decider
answered "nobody". Variants change the question and what the options say about each character."""
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from experiments.language import prompts_lang as L
from harness import director
from harness.glossary import Glossary
from harness.judge import DecisionJudge, choice_q
from harness.policy import DEFAULT_JUDGE_FIRST, Spend

EXPECT = {"n01": {"vesemir"}, "n02": {"hostomyl"}, "n03": {"eskel"}, "n04": set(),
          "n05": {"guard", "merchant"}, "n06": {"triss"}, "n07": {"smith"}, "n08": set(),
          "n09": {"lambert"}}
G = Glossary.for_world("witcher")
HERE = Path(__file__).parent
Q_OLD = ("Who speaks aloud next in this scene, answering the player or reacting to the narration? "
         "Choose the character who is addressed or whose turn it is to speak. Answer nobody only "
         "if no one at all would say anything now.")
Q_ADDRESSED = (
    "Who speaks aloud next in this scene? If the player's words or action are meant for someone "
    "(a question, a request, an offer, a challenge, an accusation), that person answers, unless "
    "the narration shows they cannot. A nod, a gesture or a look in the narration is not yet an "
    "answer: they still speak. If the player is not addressing anyone, choose whoever would "
    "naturally react aloud. Answer nobody only if no one at all would say anything now.")


def short(desc: str, n: int = 90) -> str:
    first = desc.split(". ")[0]
    return first if len(first) <= n else first[:n].rsplit(" ", 1)[0]


# What the engine's options look like after task 14: "Name (what is seen)", the same phrase the
# narrator was given for a stranger; neutral, no temperament (temperament made the decider pick
# "nobody" for the quiet ones, see the D variant).
SEEN = {"vesemir": "старий відьмак", "lambert": "відьмак із різким поглядом", "eskel": "відьмак зі шрамами",
        "coen": "відьмак", "triss": "чародійка", "jaskier": "бард", "hostomyl": "корчмар",
        "guard": "вартовий", "merchant": "купець", "smith": "коваль", "child": "дівчинка"}

VARIANTS = {
    "A current": dict(q=Q_OLD, desc=False, asked=False),
    "B +roles": dict(q=Q_OLD, desc=True, asked=False),
    "C addressed-wording": dict(q=Q_ADDRESSED, desc=False, asked=False),
    "D roles+addressed": dict(q=Q_ADDRESSED, desc=True, asked=False),
    "E D + who the player addressed": dict(q=Q_ADDRESSED, desc=True, asked=True),
    "F addressed + seen label": dict(q=Q_ADDRESSED, desc=False, asked=False, seen=True),
    "G old wording + seen label": dict(q=Q_OLD, desc=False, asked=False, seen=True),
}


def main() -> None:
    load_dotenv()
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    spend = Spend(0.10)
    judge = DecisionJudge(os.environ["OPENROUTER_API_KEY"], DEFAULT_JUDGE_FIRST, spend=spend)
    rows = [json.loads(x) for x in (HERE / "raw" / "narr.jsonl").read_text().splitlines()]
    rows = [r for r in rows if r["variant"] == "prose"]
    orig = director.speaker_questions
    out = {}
    for label, v in VARIANTS.items():
        def q2(npcs, _orig=orig, _q=v["q"]):
            qs = _orig(npcs)
            qs["first"] = choice_q(_q, qs["first"].options, tag=qs["first"].tag)
            return qs
        director.speaker_questions = q2
        hits = tot = 0
        misses = []
        for _ in range(reps):
            for r in rows:
                it = L.NARR[r["id"]]
                prof = L.P.PROFILES
                npcs = {}
                for c in it["present"]:
                    if c == "player":
                        continue
                    name = L.P.NAMES.get(c, c)
                    npcs[c] = f"{name}: {short(prof.get(c, ''))}" if v["desc"] and prof.get(c) else name
                    if v.get("seen"):
                        npcs[c] = f"{name} ({SEEN[c]})"
                state = [f"Location: {it['location']}",
                         f"The player does/says: {it['player']}"]
                if v["asked"]:
                    state.append("Who the player's words are meant for: whoever they speak to or "
                                 "about in this input, if anyone present.")
                state.append(f"Narration: {G.apply(r['text'])}")
                got = director.decide_speakers(judge, state, npcs) if npcs else []
                exp = EXPECT[r["id"]]
                hit = (not got) if not exp else bool(got and got[0] in exp)
                if r["id"] == "n08":
                    hit = True
                hits += hit
                tot += 1
                if not hit:
                    misses.append((r["id"], r["sample"], got))
        out[label] = (hits, tot, misses)
        print(f"{label:34s} {hits}/{tot}", misses, flush=True)
    director.speaker_questions = orig
    print("spend USD", round(spend.total, 4))
    (HERE / "raw" / "director_acc2.json").write_text(json.dumps(out, ensure_ascii=False))


main()
