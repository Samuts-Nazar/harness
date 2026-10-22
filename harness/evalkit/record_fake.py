"""Refresh the committed offline sessions (tests/fixtures/eval/fake_vizima.jsonl, classic
dialogue, and fake_vizima_living.jsonl, the living dialogue with NPC lines):

    nix develop --command python -m harness.evalkit.record_fake

Run it after a deliberate change of any prompt (the strict replay test fails with a miss when a
prompt changed: that is its job), then commit the new cassette."""
from __future__ import annotations

from pathlib import Path

from app.stacks import fake_stack

from .session import record

TURNS = [
    "Сідаю біля стійки й замовляю пива.",
    "Питаю корчмаря, що тут сталося позавчора.",
    "*Беру корчмаря за руку й дивлюсь йому в очі.* Скажи мені правду.",
    "Питаю вартового, що він чув про чужинця з білим волоссям.",
    "Кладу на стійку монету й питаю про кімнату на ніч.",
    "Дякую. Іду до виходу.",
]
OUT = Path(__file__).resolve().parents[2] / "tests/fixtures/eval/fake_vizima.jsonl"
OUT_LIVING = OUT.with_name("fake_vizima_living.jsonl")


def main() -> None:
    for out, dialogue in ((OUT, "classic"), (OUT_LIVING, "living")):
        if out.exists():
            out.unlink()  # a cassette appends: start it afresh
        game, rows = record(fake_stack(), TURNS, out, dialogue=dialogue)
        npc = sum(1 for e in game.transcript if e["kind"] == "npc")
        print(f"recorded {len(rows)} turns ({dialogue}, {npc} NPC lines) to {out}")


if __name__ == "__main__":
    main()
