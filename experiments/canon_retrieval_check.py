"""Retrieval check for the canon pilot: ten questions a character might face, answered from the canon
store through the knowledge filter. Prints what comes back so it can be judged by hand.

    nix develop --command python experiments/canon_retrieval_check.py <db>
"""
from __future__ import annotations

import sys

from harness.canon.retrieve import Canon

D = 1440
# (holder name as in the text, as_of minutes (day 1 00:00 = 0), question, what a correct answer looks like)
QUESTIONS = [
    ("Велерад", 1 * D + 600, "Що Ґеральт зробив у корчмі «Під Лисом»?", "knows: told by the guards / saw the aftermath"),
    ("корчмар", 1 * D, "Що написано в королівській відозві і яка нагорода?", "innkeeper never saw the scroll: empty or only the tavern fight"),
    ("Ґеральт", 0, "Звідки взялася стриґа і хто така Адда?", "before Velerad's talk: nothing"),
    ("Ґеральт", 1 * D, "Звідки взялася стриґа і хто така Адда?", "after Velerad's talk: Adda, birth, burial"),
    ("Остріт", 5 * D + 18 * 60, "Що Ґеральт знає про змову проти Фольтеста?", "at dusk, before the confrontation: nothing about Geralt's knowledge"),
    ("Остріт", 6 * D, "Що Ґеральт знає про змову проти Фольтеста?", "after the confrontation: Geralt guessed the plot"),
    ("Фольтест", 1 * D + 1380, "Як Ґеральт сказав зняти прокляття зі стриґи?", "king was told: third cockcrow, a night in the crypt"),
    ("Жмутик", 1 * D, "Що відомо про народження принцеси і Адду?", "a town guard: rumours at most, not the mayor's detail"),
    ("Велерад", 7 * D + 600, "Що відбувалося в крипті цієї ночі?", "he only knows the outcome, not the fight"),
    ("Фольтест", 7 * D + 600, "Що Остріт пропонував відьмакові?", "the king was not there: must not know"),
]


def find(canon: Canon, name: str) -> str | None:
    r = canon.con.execute("SELECT id FROM entity WHERE lower(name)=lower(?) ORDER BY type='person' DESC LIMIT 1",
                          (name,)).fetchone()
    if r:
        return r["id"]
    r = canon.con.execute("SELECT entity FROM canon_alias a JOIN entity e ON e.id=a.entity "
                          "WHERE lower(alias)=lower(?) ORDER BY e.type='person' DESC LIMIT 1", (name,)).fetchone()
    if r:
        return r["entity"]
    r = canon.con.execute("SELECT entity FROM canon_alias WHERE lower(alias) LIKE ? LIMIT 1",
                          (name.lower()[:-1] + "%",)).fetchone()
    return r["entity"] if r else None


def main(db: str) -> None:
    canon = Canon(db)
    for i, (who, as_of, q, expect) in enumerate(QUESTIONS, 1):
        hid = find(canon, who)
        print(f"\n### {i}. {who} ({hid}), as_of={as_of} (day {as_of // D + 1}), q: {q}")
        print(f"expected: {expect}")
        if not hid:
            print("  (holder not found in this store)")
            continue
        out = canon.recall(hid, q, as_of, k=4)
        print(f"  holder knows {out['n_known']} events in total by then")
        for e in out["events"]:
            print(f"  - [{e['how_known']}{'<' + e['source'] if e['source'] else ''}, learned {e['learned_t']}] {e['what'][:170]}")
        if not out["events"]:
            print("  (nothing returned)")


if __name__ == "__main__":
    main(sys.argv[1])
