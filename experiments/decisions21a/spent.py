import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import LEDGER, spent  # noqa: E402

print("probe spend USD:", round(spent(), 5), "calls:", sum(1 for _ in LEDGER.open()))
