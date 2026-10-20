"""Fact stores (immutable canon + mutable campaign) and visibility queries."""
from __future__ import annotations

import re
import sqlite3
from typing import Iterable

from .models import CAMPAIGN, CANON, HOW_VALUES, Fact, Knower


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"\w+", s.lower()) if len(t) > 2}


class FactStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # -- writes ---------------------------------------------------------
    def _insert(
        self,
        store: str,
        content: str,
        source_event_id: int | None,
        game_time: int,
        location: str,
        notability: float,
        knowers: Iterable[tuple],
    ) -> int:
        # each knower: (character, how) or (character, how, source)
        norm = [(k[0], k[1], k[2] if len(k) > 2 else None) for k in knowers]
        for _, how, _ in norm:
            if how not in HOW_VALUES:
                raise ValueError(f"bad knowledge mode: {how!r}")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO facts (store, content, source_event_id, game_time, location,"
                " notability) VALUES (?,?,?,?,?,?)",
                (store, content, source_event_id, game_time, location, notability),
            )
            fid = int(cur.lastrowid)  # type: ignore[arg-type]
            for ch, how, src in norm:
                self.conn.execute(
                    "INSERT OR IGNORE INTO fact_knowers"
                    " (fact_id, character, how, learned_at, source, event_id) VALUES (?,?,?,?,?,?)",
                    (fid, ch, how, game_time, src, source_event_id),
                )
        return fid

    def add_canon(
        self,
        content: str,
        *,
        game_time: int = 0,
        location: str = "",
        notability: float = 0.5,
        knowers: Iterable[tuple] = (),
    ) -> int:
        return self._insert(CANON, content, None, game_time, location, notability, knowers)

    def add_campaign(
        self,
        content: str,
        *,
        source_event_id: int,
        game_time: int,
        location: str,
        notability: float,
        knowers: Iterable[tuple],
    ) -> int:
        return self._insert(
            CAMPAIGN, content, source_event_id, game_time, location, notability, knowers
        )

    def add_knower(self, fact_id: int, character: str, how: str, *, learned_at: int,
                   source: str | None = None, event_id: int | None = None) -> None:
        """Someone learns an existing fact later (a rumour reaches them). Idempotent. The row
        carries the event that caused it, so rolling that event back removes the knowledge."""
        if how not in HOW_VALUES:
            raise ValueError(f"bad knowledge mode: {how!r}")
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO fact_knowers"
                " (fact_id, character, how, learned_at, source, event_id) VALUES (?,?,?,?,?,?)",
                (fact_id, character, how, learned_at, source, event_id))

    def by_source_event(self, event_id: int) -> list[Fact]:
        rows = self.conn.execute(
            f"SELECT f.* FROM facts f WHERE f.source_event_id = ? AND {self._ACTIVE} ORDER BY f.id",
            (event_id,)).fetchall()
        return self._hydrate(rows)

    # -- reads ----------------------------------------------------------
    _ACTIVE = (
        "(f.source_event_id IS NULL OR f.source_event_id NOT IN (SELECT event_id FROM rollbacks))"
    )

    def _hydrate(self, rows: list[sqlite3.Row]) -> list[Fact]:
        out: list[Fact] = []
        for r in rows:
            ks = self.conn.execute(
                "SELECT character, how, learned_at, source, event_id FROM fact_knowers WHERE fact_id=?"
                " AND (event_id IS NULL OR event_id NOT IN (SELECT event_id FROM rollbacks))"
                " ORDER BY character",
                (r["id"],),
            ).fetchall()
            out.append(
                Fact(
                    id=r["id"],
                    store=r["store"],
                    content=r["content"],
                    source_event_id=r["source_event_id"],
                    game_time=r["game_time"],
                    location=r["location"],
                    notability=r["notability"],
                    knowers=tuple(Knower(k["character"], k["how"], k["learned_at"], k["source"], k["event_id"]) for k in ks),
                )
            )
        return out

    def visible_to(
        self, character: str, at_time: int, store: str | None = None
    ) -> list[Fact]:
        """Facts `character` knows at `at_time`. Filtering is done here, in code/SQL —
        never delegated to a model."""
        sql = (
            "SELECT f.* FROM facts f JOIN fact_knowers k ON k.fact_id = f.id"
            f" WHERE k.character = ? AND k.learned_at <= ? AND {self._ACTIVE}"
            " AND (k.event_id IS NULL OR k.event_id NOT IN (SELECT event_id FROM rollbacks))"
        )
        args: list[object] = [character, at_time]
        if store:
            sql += " AND f.store = ?"
            args.append(store)
        sql += " ORDER BY f.game_time, f.id"
        return self._hydrate(self.conn.execute(sql, args).fetchall())

    def all_campaign(self, at_time: int) -> list[Fact]:
        """Full campaign state (narrator view)."""
        rows = self.conn.execute(
            f"SELECT f.* FROM facts f WHERE f.store='campaign' AND f.game_time <= ?"
            f" AND {self._ACTIVE} ORDER BY f.game_time, f.id",
            (at_time,),
        ).fetchall()
        return self._hydrate(rows)

    def get(self, fact_id: int) -> Fact | None:
        """An active fact by id (None if unknown or rolled back)."""
        rows = self.conn.execute(
            f"SELECT f.* FROM facts f WHERE f.id = ? AND {self._ACTIVE}", (fact_id,)
        ).fetchall()
        return self._hydrate(rows)[0] if rows else None

    def search_canon(self, query: str, k: int = 5) -> list[Fact]:
        """Placeholder retrieval: token overlap. Swappable for embeddings later."""
        q = _tokens(query)
        rows = self.conn.execute("SELECT f.* FROM facts f WHERE f.store='canon'").fetchall()
        scored = [(len(q & _tokens(r["content"])), r) for r in rows]
        scored = [(s, r) for s, r in scored if s > 0]
        scored.sort(key=lambda sr: (-sr[0], sr[1]["id"]))
        return self._hydrate([r for _, r in scored[:k]])
