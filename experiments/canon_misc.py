"""Small counts for the pilot report: Latin-letter names in event text, reaction listing."""
import re
import sqlite3
import sys

LAT = re.compile(r"\b(Geralt|Gerald|Velera[dl]|Foltest|Ostrit|Segel[ie]n|Segelin|Add[ay]|Vizim[a]?|Vizimir|Dalka|Medell|Temeria|Rivia)\b")
for m in ("deepseek", "luna", "qwen", "deepseek2", "luna3"):
    c = sqlite3.connect(f"file:/home/cock/projects/harness/campaigns/canon/pilot_{m}.db?mode=ro", uri=True)
    rows = [r[0] for r in c.execute("SELECT body FROM record WHERE kind='canon_event'")]
    mixed = sum(1 for b in rows if LAT.search(b))
    ua = sum(1 for b in rows if len(re.findall("[а-яіїєґ]", b.lower())) > len(b) * 0.4)
    print(m, "events", len(rows), "with Latin-spelled names", mixed, "written mostly in Ukrainian", ua)
if len(sys.argv) > 1:
    c = sqlite3.connect(f"file:/home/cock/projects/harness/campaigns/canon/pilot_{sys.argv[1]}.db?mode=ro", uri=True)
    for r in c.execute("SELECT e.name, cr.reaction, cr.attitude, substr(rec.body,1,90), cr.event_id FROM canon_reaction cr "
                       "JOIN entity e ON e.id=cr.party JOIN record rec ON rec.id=cr.id ORDER BY cr.event_id"):
        print(tuple(r))
