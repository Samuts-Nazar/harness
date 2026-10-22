"""The world never repeats the player's words or decides the player character's acts."""
from harness.player_guard import flag_player_acts, split_sentences, strip_player_quotes
from test_prose import director_judge, prose_engine
from conftest import diff

SAID = "Пані чародійко, мені сказали, що ви можете допомогти."


def test_quoted_player_line_is_removed_dash_and_guillemets():
    text = f"Двері скриплять. — {SAID} Чародійка підводить очі."
    out, removed = strip_player_quotes(text, f"Входжу й кажу: «{SAID}»")
    assert SAID not in out and "Двері скриплять." in out and "Чародійка підводить очі." in out
    assert len(removed) == 1
    out2, r2 = strip_player_quotes(f"Ти кажеш: «{SAID}» Тиша.", SAID)
    assert out2 == "Тиша." and r2


def test_other_quotes_and_unrelated_text_are_kept():
    t = "На вивісці написано «Під Лисом». Ти йдеш далі."
    assert strip_player_quotes(t, "Іду на ринок") == (t, [])
    assert strip_player_quotes(t, "Іду під лисом") == (t, [])  # short overlap is not a repeat


def test_flag_finds_acts_not_perception():
    s = ["Ти кладеш гаманець до кишені.", "Ти чуєш далекий дзвін.", "Тебе нудить.",
         "Ти стояв на порозі.", "Ти бачиш мокрий брук.", "Рейнар відкриває двері.",
         "Мирослав бере хліб."]
    assert flag_player_acts(s, "Мирослав") == [0, 3, 6]


def test_split_sentences_roundtrip():
    t = "Раз. Два!\nТри?"
    assert "".join(split_sentences(t)) == t


def _run(narr, player, verdict):
    judge = director_judge("innkeeper", player_act=verdict)
    eng, _ = prose_engine({"narrator": [narr], "extractor": ["none", diff()], "npc": ["Ну."]},
                          judge=judge)
    res = eng.turn(player)
    return eng, res, judge


def test_engine_drops_flagged_sentence_the_judge_confirms():
    eng, res, j = _run("Дощ. Ти кладеш гаманець до кишені. Ти чуєш дзвін.", "Іду на ринок",
                       lambda q, st: "гаманець" in q.text)
    assert "гаманець" not in res.narration and "Ти чуєш дзвін." in res.narration
    drops = [n for n in eng.devlog if n["kind"] == "narrator_player_action_dropped"]
    assert len(drops) == 1 and "гаманець" in drops[0]["sentence"]
    asks = [a for a in j.asked if any(q.tag == "player_act" for q in a[1].values())]
    assert len(asks) == 1, "one batched call"


def test_engine_keeps_sentence_when_judge_says_entailed():
    eng, res, _ = _run("Ти йдеш на ринок.", "Іду на ринок", lambda q, st: False)
    assert "Ти йдеш на ринок." in res.narration
    assert not [n for n in eng.devlog if n["kind"] == "narrator_player_action_dropped"]


def test_engine_removes_player_quote_without_judge_call():
    eng, res, j = _run(f"Двері скриплять. — {SAID} Тиша.", f"Входжу й кажу: «{SAID}»",
                       lambda q, st: False)
    assert SAID not in res.narration
    assert any(n["kind"] == "narrator_player_action_dropped" and n.get("why") == "player_quote"
               for n in eng.devlog)
