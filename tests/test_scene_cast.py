"""Task LD-9: characters the narration brings into a scene. After the narrator (before delivery)
the people the narration shows present who are not in the scene are found; a canon person is
checked against the canon calendar (elsewhere: the narration is drift, regenerated with a note),
anyone who can be here is admitted to the scene so they can speak and the director can pick
them. Names stay knowledge. Fake providers and a fake canon calendar."""

import pytest

from canon_fixture import make_store
from harness.canon.play import CanonCast, CanonPlay
from harness.canon.retrieve import Canon
from harness.director import EXCHANGE_HEADER, NOBODY, PLAYER_FLOOR
from harness.judge import FakeJudge
from harness.models import PLAYER, SCENE_ENTRY, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from harness.scene_cast import ELSEWHERE, HERE, UNKNOWN, SceneCast, Whereabouts, parse_people
from conftest import diff

PROFILES = [
    CharacterProfile(PLAYER, "Рагнар", "Мандрівник.", appearance="молодий незнайомець із мечем"),
    CharacterProfile("horst", "Горст", "Корчмар.", appearance="кремезний сивий корчмар"),
    CharacterProfile("myrra", "Мірра", "Торговка з ринку.", appearance="жінка з ринку"),
]
GERALT_LOOK = "сивий чоловік із двома мечами"


class Calendar:
    """A fake canon calendar: one canon person, Ґеральт, and where canon puts him."""

    def __init__(self, status: str, reason: str = "") -> None:
        self.status, self.reason = status, reason
        self.asked: list[tuple[str, int]] = []

    def identify(self, mention: str) -> str | None:
        return "char:geralt" if "ґеральт" in mention.lower() else None

    def cid(self, entity: str) -> str:
        return "geralt"

    def whereabouts(self, entity: str, t: int, here_place: str | None, here_name: str
                    ) -> Whereabouts:
        self.asked.append((entity, t))
        return Whereabouts(self.status, self.reason)

    def describe(self, entity: str) -> str:
        return "Ґеральт, a witcher"

    def admit(self, eng: Engine, entity: str) -> str:
        eng.profiles["geralt"] = CharacterProfile("geralt", "Ґеральт", "A witcher, a stranger "
                                                  "here.", appearance=GERALT_LOOK)
        return "geralt"


def director(addressed: dict[str, str]):
    """The scene director as a rule: an NPC the player's own words address takes the floor once,
    then the floor goes back to the player; nobody otherwise."""
    def rule(q, state):
        said = next((str(x) for x in state if str(x).startswith("The player does/says:")), "")
        if any(str(x).startswith(EXCHANGE_HEADER) for x in state):
            return PLAYER_FLOOR
        for cid, word in addressed.items():
            if cid in q.options and word in said.lower():
                return cid
        return NOBODY
    return rule


def make(narrations, lister, *, npc=(), status=HERE, reason="", source=None, rules=None,
         extractor_tail=None, **kw):
    """`lister`: the newcomer lister's answers (extractor model), one per narration attempt;
    the actions lister and the diff follow per turn (`extractor_tail`)."""
    tail = extractor_tail if extractor_tail is not None else ["none", diff()]
    script = {"narrator": list(narrations), "npc": list(npc),
              "extractor": [*lister, *tail]}
    judge = FakeJudge({"director_narration": True, "director_next": NOBODY, **(rules or {})})
    prov = FakeProvider(script=script)
    kw.setdefault("record_language", None)
    eng = Engine(prov, PROFILES, Scene("корчма «Під Совою»", (PLAYER, "horst"), time=0),
                 models=ModelConfig(), judge=judge, narration="prose", **kw)
    cal = source if source is not None else Calendar(status, reason)
    eng.scene_cast = SceneCast(cal, culture="northern")
    return eng, prov, judge, cal


def narrator_prompts(prov):
    return ["\n".join(x["content"] for x in m) for mod, m in prov.calls if mod == "narrator"]


# -- the brief's two tests ----------------------------------------------------------------------
def test_narrator_cannot_place_absent_canon_character():
    eng, prov, judge, cal = make(
        ["Біля стійки сидить Ґеральт і п'є пиво.", "Дощ стукає у вікна корчми."],
        ["Ґеральт", "none"], status=ELSEWHERE,
        reason="in canon he is at the city gate at this hour")
    res = eng.turn("*Озираюсь.*")
    assert res.narration == "Дощ стукає у вікна корчми."
    assert "geralt" not in eng.scene.present and "geralt" not in eng.profiles
    prompts = narrator_prompts(prov)
    assert len(prompts) == 2
    assert "Ґеральт" in prompts[1] and "city gate" in prompts[1]  # regenerated with a note
    assert cal.asked == [("char:geralt", 0)]
    assert any(n["kind"] == "narrator_absent_character" for n in eng.devlog)
    assert not eng.log.active([SCENE_ENTRY])  # nobody entered


def test_admitted_character_can_be_addressed_and_answers():
    eng, prov, judge, cal = make(
        ["Біля стійки сидить Ґеральт і п'є пиво.", "Корчмар витирає стійку."],
        ["Ґеральт"], status=HERE,
        npc=["— Здалеку."],
        rules={"director_next": director({"geralt": "сивий"})},
        # turn 1: actions, diff; turn 2: the lister (nobody new), actions, diff
        extractor_tail=["none", diff(), "none", "none", diff()])
    res1 = eng.turn("*Озираюсь.*")
    assert "geralt" in eng.scene.present
    # names stay knowledge: the player character does not know him yet
    assert "Ґеральт" not in res1.narration and GERALT_LOOK in res1.narration
    assert [e.payload["character"] for e in eng.log.active([SCENE_ENTRY])][-1] == "geralt"
    res2 = eng.turn("Гей, сивий, звідки ти?")
    assert [u.payload["speaker"] for u in res2.utterances] == ["geralt"]
    asks = [qs["next"].options for _, qs in judge.asked if "next" in qs]
    assert "geralt" in asks[-1]


# -- more cases -----------------------------------------------------------------------------------
def test_people_already_present_or_only_mentioned_are_not_admitted():
    eng, prov, judge, cal = make(["Корчмар наливає пиво."], ["кремезний сивий корчмар\nnone"])
    eng.turn("*Озираюсь.*")
    assert eng.scene.present == (PLAYER, "horst")
    assert parse_people("- none\n") == []
    assert parse_people("1. худий хлопчик\n- Ґеральт (named)\n") == ["худий хлопчик", "Ґеральт"]


def test_invented_passer_by_is_admitted_with_a_generated_profile():
    eng, prov, judge, cal = make(["Двері рипнули: увійшов худий хлопчик-посильний."],
                                 ["худий хлопчик-посильний"])
    eng.turn("*Озираюсь.*")
    new = [c for c in eng.scene.present if c not in (PLAYER, "horst")]
    assert len(new) == 1
    prof = eng.profiles[new[0]]
    assert prof.appearance == "худий хлопчик-посильний" and prof.core  # npcgen: name, core
    assert eng.names.hidden(new[0]) and not eng.names.knows(PLAYER, new[0])
    assert prof.name not in eng.log.active(["narration"])[-1].payload["text"]


def test_known_npc_elsewhere_is_drift_and_nearby_npc_walks_in():
    where = {"myrra": "market"}
    eng, prov, judge, cal = make(["Мірра сидить за столом.", "Тихо."], ["Мірра", "none"])
    eng.scene_cast = SceneCast(cal, culture="northern", where=lambda c: where.get(c),
                               here=lambda: "tavern")
    eng.acquaint(PLAYER, "myrra")
    eng.turn("*Озираюсь.*")
    assert "myrra" not in eng.scene.present
    assert "Мірра" in narrator_prompts(prov)[1]
    eng2, *_ = make(["Мірра заходить із вулиці."], ["Мірра"])
    eng2.scene.outside = ("myrra",)
    eng2.acquaint(PLAYER, "myrra")
    eng2.turn("*Озираюсь.*")
    assert "myrra" in eng2.scene.present and "myrra" not in eng2.scene.outside


def test_unknown_whereabouts_go_to_a_plausibility_judgment():
    eng, prov, judge, cal = make(["Біля стійки сидить Ґеральт.", "Тихо."], ["Ґеральт", "none"],
                                 status=UNKNOWN, rules={"cast_plausible": False})
    eng.turn("*Озираюсь.*")
    assert "geralt" not in eng.scene.present
    assert any(q.tag == "cast_plausible" for _, qs in judge.asked for q in qs.values())
    eng2, *_ = make(["Біля стійки сидить Ґеральт."], ["Ґеральт"], status=UNKNOWN,
                    rules={"cast_plausible": True})
    eng2.turn("*Озираюсь.*")
    assert "geralt" in eng2.scene.present


@pytest.mark.parametrize("parallel", [False, True])
def test_admission_is_undone_when_the_narration_is_rejected_later(parallel):
    calls = {"n": 0}

    def speech(q, state):
        calls["n"] += 1
        return calls["n"] == 1  # the first narration "contains speech"

    eng, prov, judge, cal = make(["Ґеральт каже, що втомився.", "Тихо."], ["Ґеральт", "none"],
                                 rules={"narrator_speech": speech}, parallel=parallel,
                                 extractor_tail=["none", "none", diff()] if parallel else None)
    res = eng.turn("*Озираюсь.*")
    assert res.narration == "Тихо."
    assert "geralt" not in eng.scene.present  # the canon profile may stay made, unseen
    assert not eng.log.active([SCENE_ENTRY])


def test_without_scene_cast_no_extra_call():
    prov = FakeProvider(script={"narrator": ["Ґеральт п'є."], "extractor": ["none", diff()]})
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "horst"), time=0), models=ModelConfig(),
                 judge=FakeJudge({"director_narration": True, "director_next": NOBODY}),
                 narration="prose", record_language=None)
    eng.turn("*Озираюсь.*")
    assert [m for m, _ in prov.calls].count("extractor") == 2


# -- the canon calendar on the fixture store ------------------------------------------------------
@pytest.fixture
def canon():
    con, _ = make_store()
    return Canon(con)


def test_canon_cast_reads_where_a_person_is_from_the_calendar(canon):
    play = CanonPlay.at(canon, 5, 11, "place:owl")  # an hour before Ярош speaks at the town hall
    cc = CanonCast(play, places={"place:owl": "tavern", "place:hall": "hall"})
    assert cc.identify("Ярош стоїть біля дверей") == "char:yarosh"
    assert cc.identify("худий хлопчик") is None
    assert cc.identify("ратуша") is None  # a place is not a person
    w = cc.whereabouts("char:yarosh", 0, "tavern", "корчма «Під Совою»")
    assert w.status == ELSEWHERE and "ратуш" in w.reason
    w = cc.whereabouts("char:mirko", 0, "tavern", "")
    assert w.status == UNKNOWN and "Під Совою" in w.reason  # last seen there, days ago
    play2 = CanonPlay.at(canon, 2, 20, "place:owl")  # Мірко came to the tavern an hour ago
    cc2 = CanonCast(play2)
    assert cc2.whereabouts("char:mirko", 0, None, "корчма «Під Совою»").status == HERE


def test_canon_cast_admits_with_a_canon_profile(canon):
    play = CanonPlay.at(canon, 2, 20, "place:owl")
    eng = Engine(FakeProvider(), [CharacterProfile(PLAYER, "Рагнар", "")],
                 Scene("корчма «Під Совою»", (PLAYER,), time=0), judge=FakeJudge())
    play.ensure_character(eng, "char:bart")
    cc = CanonCast(play)
    cid = cc.admit(eng, "char:mirko")
    assert cid == "mirko" and eng.profiles["mirko"].name == "Мірко"
    assert play.made["char:mirko"] == "mirko"
    assert eng.names.knows("bart", "mirko")  # met in canon before the start


def test_undone_passer_by_leaves_no_profile():
    calls = {"n": 0}

    def speech(q, state):
        calls["n"] += 1
        return calls["n"] == 1

    eng, *_ = make(["Хлопчик-посильний каже, що втомився.", "Тихо."],
                   ["хлопчик-посильний", "none"], rules={"narrator_speech": speech})
    eng.turn("*Озираюсь.*")
    assert set(eng.profiles) == {p.id for p in PROFILES}
    assert eng.scene.present == (PLAYER, "horst")
