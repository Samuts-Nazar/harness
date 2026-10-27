"""The finished canon store for «Кров ельфів» (task 8b) works for the game.

Needs the local store (campaigns/canon/be.db, git-ignored) and data/ (never committed): skipped when
either is absent, e.g. in CI. Queries are written for the test; no book text here.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from harness.canon.retrieve import Canon

ROOT = Path(__file__).resolve().parent.parent
_CANDIDATES = [ROOT / "campaigns/canon/be.db", Path("/home/cock/projects/harness/campaigns/canon/be.db")]
DB = next((p for p in _CANDIDATES if p.exists()), None)
DATA = ROOT / "data" / "witcher_books.txt"

pytestmark = pytest.mark.skipif(DB is None or not DATA.exists(),
                                reason="local canon store be.db or data/ is absent")

YEN, CIRI, NENNEKE = "char:yennefer", "char:ciri", "char:nenneke"
DAY = 1440
LATE = 22 * DAY + 12 * 60      # day 23 noon: after the departure on day 22, the end of the arc
CH7_NOON = 20 * DAY + 12 * 60  # day 21 noon: chapter 7 present, before the afternoon talk and the departure


@pytest.fixture(scope="module")
def canon() -> Canon:
    return Canon(DB)


@pytest.fixture(scope="module")
def con() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def test_counts_and_cast(con: sqlite3.Connection) -> None:
    assert con.execute("SELECT COUNT(*) FROM canon_event").fetchone()[0] >= 200
    ids = {r[0] for r in con.execute("SELECT id FROM entity")}
    assert {YEN, CIRI, NENNEKE, "place:temple-of-melitele"} <= ids
    # every event has a search row and a source offset (the finish script ran)
    assert con.execute("SELECT COUNT(*) FROM canon_event_fts").fetchone()[0] == \
        con.execute("SELECT COUNT(*) FROM canon_event").fetchone()[0]
    assert con.execute("SELECT COUNT(*) FROM canon_event WHERE src_from IS NULL").fetchone()[0] == 0


def test_present_participants_are_knowers(con: sqlite3.Connection) -> None:
    missing = con.execute(
        "SELECT COUNT(*) FROM canon_participant p JOIN entity e ON e.id=p.entity "
        "WHERE p.role IN ('actor','target','victim','speaker','listener','witness') "
        "AND e.type IN ('person','collective','creature') AND NOT EXISTS "
        "(SELECT 1 FROM canon_knower k WHERE k.event_id=p.event_id AND k.entity=p.entity)").fetchone()[0]
    assert missing == 0


def test_yennefer_recalls_the_temple_late(canon: Canon, con: sqlite3.Connection) -> None:
    got = canon.recall(YEN, "що сталося в храмі Мелітеле з Неннеке", LATE)
    assert got["profile"] is not None and got["n_known"] > 0
    assert len(got["events"]) >= 1
    for e in got["events"]:
        row = con.execute("SELECT learned_t FROM canon_knower WHERE event_id=? AND entity=?", (e["id"], YEN)).fetchone()
        assert row is not None and row["learned_t"] <= LATE


def test_recall_without_embedder_is_fts_only(canon: Canon) -> None:
    # the game opens Canon(path) with no embedder: no vectors are loaded and recall still answers
    assert canon.embedder is None and canon._load_vecs() == {}
    assert canon.recall(YEN, "яблучний пиріг з корицею", LATE)["events"] == []


def test_ciri_does_not_know_what_she_never_saw(canon: Canon, con: sqlite3.Connection) -> None:
    q = "Вільгефорц Терранова Тіссая радяться про королів"
    hits = [e["id"] for e in canon.search_unfiltered(q)]
    assert hits, "the unfiltered search must find the mages' talk, or this test proves nothing"
    ciri_knows = {r[0] for r in con.execute("SELECT event_id FROM canon_knower WHERE entity=?", (CIRI,))}
    unseen = [h for h in hits if h not in ciri_knows]
    assert unseen
    got = {e["id"] for e in canon.recall(CIRI, q, LATE)["events"]}
    assert not got & set(unseen)


def test_ciri_does_not_know_before_she_learns(canon: Canon, con: sqlite3.Connection) -> None:
    q = "Цірі і Йеннефер розмовляють про від'їзд і війну"
    hits = [e["id"] for e in canon.search_unfiltered(q, k=10)]
    later = [h for h in hits if (r := con.execute(
        "SELECT learned_t FROM canon_knower WHERE event_id=? AND entity=?", (h, CIRI)).fetchone())
        and r["learned_t"] > CH7_NOON]
    assert later, "need an event Ciri learns after day 21 noon"
    early = canon.recall(CIRI, q, CH7_NOON, k=10)
    assert not {e["id"] for e in early["events"]} & set(later)
    assert all(e["learned_t"] <= CH7_NOON for e in early["events"])
    after = canon.recall(CIRI, q, LATE, k=10)
    assert {e["id"] for e in after["events"]} & set(later)
