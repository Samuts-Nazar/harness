"""Refresh the committed offline session (tests/fixtures/eval/fake_vizima.jsonl):

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


def main() -> None:
    game, rows = record(fake_stack(), TURNS, OUT)
    print(f"recorded {len(rows)} turns to {OUT}")


if __name__ == "__main__":
    main()
