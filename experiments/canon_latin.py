"""Capitalised Latin words (and Latin letters inside Cyrillic words) in event text, per pilot store."""
import re
import sqlite3
import sys
from collections import Counter

c = sqlite3.connect(f"file:/home/cock/projects/harness/campaigns/canon/pilot_{sys.argv[1]}.db?mode=ro", uri=True)
cnt = Counter()
for (b,) in c.execute("SELECT body FROM record WHERE kind='canon_event'"):
    for w in re.findall(r"\b[A-Z][a-z]+(?:'[a-z]+)?\b", b):
        cnt[w] += 1
    for w in re.findall(r"\b\w*[A-Za-z]\w*[а-яіїєґА-ЯІЇЄҐ]\w*\b|\b\w*[а-яіїєґА-ЯІЇЄҐ]\w*[A-Za-z]\w*\b", b):
        cnt["MIXED:" + w] += 1
print(cnt.most_common(70))
