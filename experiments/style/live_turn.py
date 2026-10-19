"""One live turn through the real engine with the style on (luna etc.): shows the stored speech,
the NPC beats as actions, manner notes and the cost. PYTHONPATH=. python -m experiments.style.live_turn"""
import os
import tempfile

from dotenv import load_dotenv

load_dotenv("/home/cock/projects/harness/.env")

from app.campaigns import open_campaign  # noqa: E402
from app.stacks import live_stack  # noqa: E402
from harness.models import ACTION, UTTERANCE  # noqa: E402

stack = live_stack(0.15)
camp = open_campaign(stack, root=tempfile.mkdtemp(prefix="t15-"), new=True)
eng = camp.engine
res = eng.turn("Сідайте. Я слухаю вас.")
print("NARRATION:", res.narration, "\n")
for u in res.utterances:
    print("UTTERANCE", u.payload["speaker"], "\n", u.payload["text"], "\n  speech only:", u.payload.get("speech"), "\n")
print("ACTIONS:")
for a in eng.log.active([ACTION]):
    print(" -", a.payload.get("by", "-"), a.payload["text"])
print("MANNERS:", {k: v.manner[:80] for k, v in eng.profiles.items()})
print("NOTES:", [n["kind"] for n in eng.devlog])
print("SPEND:", round(getattr(stack.spend, "total", 0), 4))
