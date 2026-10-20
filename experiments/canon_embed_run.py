"""Embed the events of pilot_v3.db with a given model and report retrieval on the 10 questions + extras.

    PYTHONPATH=. python3 experiments/canon_embed_run.py baai/bge-m3
"""
import sqlite3
import sys

from dotenv import load_dotenv

from harness.canon.embed import OpenRouterEmbedder, cosine, pack, unpack
from harness.canon.refine import event_embed_text

load_dotenv(".env")
model = sys.argv[1]
emb = OpenRouterEmbedder(model)
con = sqlite3.connect("campaigns/canon/pilot_v3.db")
con.row_factory = sqlite3.Row
con.execute("CREATE TABLE IF NOT EXISTS canon_embedding (event_id INTEGER NOT NULL, model TEXT NOT NULL, dim INTEGER NOT NULL, "
            "vec BLOB NOT NULL, PRIMARY KEY (event_id, model))")
rows = list(con.execute("SELECT r.id, r.body, c.gist_uk, c.kw_uk, c.quote FROM record r JOIN canon_event c ON c.id=r.id"))
vecs = emb.embed([event_embed_text(r["gist_uk"], r["kw_uk"], r["body"]) for r in rows])
for r, v in zip(rows, vecs):
    con.execute("INSERT OR REPLACE INTO canon_embedding VALUES (?,?,?,?)", (r["id"], model, len(v), pack(v)))
con.commit()
print(model, "events", len(rows), "tokens", emb.tokens)
QS = [
    "Що Ґеральт зробив у корчмі «Під Лисом»?", "Що написано в королівській відозві і яка нагорода?",
    "Звідки взялася стриґа і хто така Адда?", "Що Ґеральт знає про змову проти Фольтеста?",
    "Як Ґеральт сказав зняти прокляття зі стриґи?", "Що відбувалося в крипті цієї ночі?",
    "Що Остріт пропонував відьмакові?", "Яка погода в Новіграді і скільки коштує хліб?",
    "Хто такий Йорвет і де сховалась ельфійська банда?"]
for q in QS:
    qv = emb.embed([q])[0]
    sc = sorted(((cosine(qv, unpack(r["vec"])), r["event_id"]) for r in con.execute(
        "SELECT event_id, vec FROM canon_embedding WHERE model=?", (model,))), reverse=True)[:4]
    print(f"\n{q}")
    for s, i in sc:
        g = con.execute("SELECT gist_uk FROM canon_event WHERE id=?", (i,)).fetchone()[0]
        print(f"  {s:.3f} #{i} {g[:90]}")
