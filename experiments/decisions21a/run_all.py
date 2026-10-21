"""Run every probe method once (task 21A), from the repo root: nix develop --command python experiments/decisions21a/run_all.py"""
import subprocess
import sys
from pathlib import Path

METHODS = ["dec:liquid/d1-ultra+eq+noscene", "llm+eq+noscene", "dec:liquid/d1-ultra+eq", "dec:liquid/d1-ultra+eq+state",
           "dec:perplexity/pplx-decider-v1.2+eq", "dec:microsoft/microsoft-decision-1+eq", "llm+eq", "llm+eq+state",
           "vs+eq", "vs+eq+state", "dec:liquid/d1-ultra+eq+anon", "llm+eq+anon"]
here = Path(__file__).parent
for m in METHODS:
    r = subprocess.run([sys.executable, str(here / "run.py"), m, "--n", "5"], capture_output=True, text=True)
    print(m, "->", (r.stdout.strip() or r.stderr.strip()[-300:]), flush=True)
subprocess.run([sys.executable, str(here / "spent.py")])
