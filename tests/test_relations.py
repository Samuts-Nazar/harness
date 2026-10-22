"""Character portraits task 3: the NPC -> player relationship in the event log, and the judges
(director, outcome) that see it."""
from test_portrait_context import PROFILES, eng, prompt

from app.newgame import rung_seed
from harness.judge import FakeJudge
from harness.models import PLAYER, UTTERANCE, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from harness.relations import Relations

SC = Scene("Рінде", (PLAYER, "yen"), 0)


def test_default_relationship_is_stranger():
    e = eng()
    r = Relations(e.log).get("yen", PLAYER)
    assert (r.rung, r.warmth, r.trust, r.reason, r.event_id) == ("stranger", -0.2, 0.2, "", None)


def test_no_event_default_follows_the_stored_seed_and_agrees_with_the_line():
    e = eng()
    e.bind_portrait("yen", "p_yen", rung="ally")
    for ev in e.log.active(["relation"]):          # an old campaign: only rung_seeds remain
        e.log.rollback(ev.id)
    r = e.ctx.relations.get("yen", PLAYER)
    assert (r.rung, r.warmth, r.trust, r.event_id) == ("ally", 0.5, 0.6, None)
    assert "ally, warmth 0.5, trust 0.6" in e.ctx.relation_line("yen")


def test_seed_values_cover_every_seedable_rung_and_unknown_raises():
    from harness.relations import SEED_VALUES
    assert SEED_VALUES["close"] == (0.7, 0.7) and SEED_VALUES["lover"] == (0.9, 0.85)
    e = eng()
    import pytest
    with pytest.raises(ValueError):
        Relations(e.log).seed("yen", PLAYER, "nonsense", SC)


def test_bind_portrait_does_not_reseed_over_an_existing_relation():
    e = eng()
    e.bind_portrait("yen", "p_yen", rung="client")
    Relations(e.log).set("yen", PLAYER, "close", 0.8, 0.7, "earned", SC, None)
    n = len(e.log.active(["relation"]))
    e.bind_portrait("yen", "p_yen", rung="stranger")
    assert len(e.log.active(["relation"])) == n
    assert e.ctx.rung_of("yen") == "close"


def test_set_and_get_latest():
    e = eng()
    rel = Relations(e.log)
    rel.set("yen", PLAYER, "client", 0.1, 0.4, "paid", SC, None)
    ev = rel.set("yen", PLAYER, "ally", 0.5, 0.6, "helped", SC, None)
    r = rel.get("yen", PLAYER)
    assert (r.rung, r.warmth, r.trust, r.reason, r.event_id) == ("ally", 0.5, 0.6, "helped", ev.id)
    assert rel.get("inn", PLAYER).rung == "stranger"      # per pair


def test_rollback_of_cause_reverts_relationship():
    e = eng()
    rel = Relations(e.log)
    rel.set("yen", PLAYER, "client", 0.1, 0.4, "paid", SC, None)
    utt = e.log.append(UTTERANCE, game_time=1, location="Рінде",
                       payload={"speaker": PLAYER, "text": "Дякую."})
    rel.set("yen", PLAYER, "close", 0.8, 0.7, "kindness", SC, utt.id)
    assert rel.get("yen", PLAYER).rung == "close"
    e.log.rollback(utt.id)
    assert rel.get("yen", PLAYER).rung == "client"


def test_survives_reopen(tmp_path):
    prov = FakeProvider(script={})
    e = Engine.create_campaign("c", prov, PROFILES, SC, root=tmp_path, models=ModelConfig(),
                               judge=FakeJudge(), world="witcher")
    e.bind_portrait("yen", "yennefer_rinde", rung="client")
    Relations(e.log).set("yen", PLAYER, "ally", 0.5, 0.6, "helped", e.scene, None)
    e.close()
    again = Engine.open_campaign("c", prov, root=tmp_path, models=ModelConfig(),
                                 judge=FakeJudge())
    assert Relations(again.log).get("yen", PLAYER).rung == "ally"
    assert again.ctx.rung_of("yen") == "ally"


def test_reopen_old_campaign_falls_back_to_stored_seeds(tmp_path):
    prov = FakeProvider(script={})
    e = Engine.create_campaign("c", prov, PROFILES, SC, root=tmp_path, models=ModelConfig(),
                               judge=FakeJudge(), world="witcher")
    e.bind_portrait("yen", "yennefer_rinde", rung="client")
    for ev in e.log.active(["relation"]):                         # made before the store
        e.log.rollback(ev.id)
    e.close()
    again = Engine.open_campaign("c", prov, root=tmp_path, models=ModelConfig(),
                                 judge=FakeJudge())
    assert again.ctx.rung_of("yen") == "client"


def test_package_attitude_seeds_rung():
    assert rung_seed({"knows_player": True, "attitude": "добрий друг, радий тебе бачити"}) == "ally"
    assert rung_seed({}) == "stranger"
    e = eng()
    e.bind_portrait("yen", "p_yen", rung=rung_seed({"knows_player": True,
                                                    "attitude": "радо вітає друга"}))
    assert Relations(e.log).get("yen", PLAYER).rung == "ally"
    assert e.ctx.rung_of("yen") == "ally"
    e2 = eng()
    e2.bind_portrait("yen", "p_yen", rung=rung_seed({}))
    assert Relations(e2.log).get("yen", PLAYER).rung == "stranger"


def test_relation_line_format():
    e = eng()
    e.bind_portrait("yen", "p_yen")
    assert e.ctx.relation_line("yen", e.scene) == \
        "Йеннефер → the player: stranger, warmth -0.2, trust 0.2; stance: test"


def test_director_and_outcome_see_relation_line():
    j = FakeJudge(yes=True)
    e = eng()
    e.judge = j
    e.bind_portrait("yen", "p_yen")
    line = e.ctx.relation_line("yen", e.scene)
    assert line in "\n".join(e.ctx.director_state(e.scene, "Привіт.", ""))
    e.outcome_judge.player("Б'ю її.", unbounded=False)
    assert any(line in "\n".join(state) for state, _ in j.asked)


def test_relation_line_not_in_narrator_or_player_text():
    import json
    from harness import assistant
    e = eng()
    e.bind_portrait("yen", "p_yen")
    line = e.ctx.relation_line("yen", e.scene)
    assert "warmth" in prompt(e, "yen")                     # the NPC itself sees its standing
    assert "warmth" not in prompt(e, "inn")
    narr = json.dumps(e.ctx.narrator(e.scene, "Привіт."), ensure_ascii=False)
    assert "warmth" not in narr and "→ the player" not in narr and line not in narr
    sug = json.dumps(assistant.context(e), ensure_ascii=False, default=str)
    assert "warmth" not in sug and line not in sug
