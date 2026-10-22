"""Round 2 of the blind writing test (task 22b): six NEW moments, GLM re-run with a fix, glm-5.3-flash,
mistral-large-4-0 and the two mimo anchors.

The moments (Vizima pilot, Ukrainian) are built with the engine's own ContextBuilder, the Witcher style sheet
(no book exemplars) and hand-written NPC manner notes in the format of task 15 (generated notes are one model
call each; these are written once here, English, like the generator's output). Two moments are chains of two
calls to the same model (an exchange of two locals; narration, then the innkeeper). Glitch filter, temperature
0.8 and the page format are those of round 1 (run.py is imported, not copied). Two samples per model per
moment, streamed to measure the first token. Raw: experiments/human_ab/raw/out2.jsonl (resumable).

    PYTHONPATH=. nix develop --command python -m experiments.human_ab.run2 [--probe MODEL] [--build-only]

Spend cap 0.14 USD through the ledger of experiments/common/llm.py (experiment "task22b").
"""
import json
import random
import sys
import time
from dataclasses import replace

import httpx

from experiments.common import llm
from experiments.human_ab import run as R
from harness.glossary import Glossary
from harness.models import NARRATION, PLAYER, CharacterProfile, Scene
from harness.outcome import FAILS, Outcome
from harness.pipeline import Engine
from harness.profile import load_profile
from harness.providers import FakeProvider
from harness.style import Style

RAW2 = R.RAW / "out2.jsonl"
EXP, CAP = "task22b", 0.14
SAMPLES = 2
SAMPLES_OF = {"w0": 3}  # the most important scene gets a third sample

# model -> extra request fields. The GLM fix is found by --probe, see reports/human_ab/README2.md.
GLM_FIX = {"reasoning": {"effort": "low", "exclude": True}}  # GLM-5.3 endpoints refuse reasoning off
MODELS = {
    "z-ai/glm-5.3": GLM_FIX,
    "z-ai/glm-5.3-flash": GLM_FIX,
    "mistralai/mistral-large-4-0": {"reasoning": {"enabled": False}},
    "xiaomi/mimo-v2.6-flash": {"reasoning": {"enabled": False}},
    "xiaomi/mimo-v2.6-pro": {"reasoning": {"enabled": False}},
}

# ---------------------------------------------------------------------------------------------
# The moments
# ---------------------------------------------------------------------------------------------
G = Glossary.for_world("witcher")
STYLE = Style.load("witcher", exemplars=False)
NIGHT = 3 * 24 * 60 + 22 * 60
ME = CharacterProfile(PLAYER, "Рагнар", "Мандрівник, відьмак.", appearance="чужинець із жовтими очима і срібним мечем")

MANNER = {
    "yarosh": "Dry, clipped sentences; throws the other man's own words back with a twist. Never raises his "
              "voice. Rubs his unshaven jaw; holds a cup of beer gone cold that he does not drink. Calls a "
              "suspect «шановний» when most contemptuous. When pressed, drifts to his bad knee and the "
              "night shift.",
    "myron": "Loud, sure of himself, speaks in big pictures: «чув від одного возія», «так усі кажуть». "
             "Slaps the table to end a point. Adds a detail every time he is doubted, each one worse. Swears "
             "by his horses.",
    "hanna": "Quick, dry, practical. Answers a tale with a price or a chore. Never repeats herself; cuts "
             "him off mid-sentence. Wipes her hands on her apron while she talks. Believes in debts, not "
             "monsters.",
    "orysia": "Slow, sideways speech; answers a question with a remark about the weather or the herbs. "
              "Never names a thing straight: «воно», «те, що ходить». Ends a thought with a saying, "
              "half-remembered. Touches the bundle at her belt when afraid.",
    "yen": "Precise, ironic, formally mocking address («пане», «шановний гостю» said like an insult). Short "
           "cutting lines, never a speech; no pathos, no pleading, no explaining herself. Lets silence do "
           "half the work. Power held back, not shown: a raised eyebrow, a turned ring, a cooling of the "
           "air, never a flourish. Names her price early and flatly. Asks a question that tests the "
           "visitor. Rarely, one line comes out too soft or too fast, and she covers it with a sneer.",
    "ostap": "Heavy, grudging. Counts damage aloud, in coins. Speaks to the guests as little as he can "
             "and to his furniture as if it were a wounded relative. Polishes a mug, even a broken one.",
}


def _eng(location: str, npcs: list[CharacterProfile], sc_present: tuple[str, ...],
         me: CharacterProfile = ME) -> Engine:
    eng = Engine(FakeProvider(), [me, *npcs], Scene(location, sc_present, NIGHT), glossary=G, style=STYLE,
                 narration="prose", outcomes=True, world_profile=load_profile("witcher"))
    for p in npcs:
        eng.profiles[p.id] = replace(p, manner=MANNER.get(p.id, ""))
    return eng


def _narr(eng: Engine, *texts: str) -> None:
    for t in texts:
        eng._event(NARRATION, [], {"text": t}, witnesses=eng.scene.present)


def _narrator_msgs(eng: Engine, player_input: str, outcome: str | None = None) -> list[dict[str, str]]:
    eng.ctx.narration = "prose"
    return eng.ctx.narrator(eng.scene, player_input, outcome)


def _npc_msgs(eng: Engine, npc: str) -> list[dict[str, str]]:
    return eng.ctx.character_view(npc, eng.scene).messages()


YEN = CharacterProfile(
    "yen", "Єніфер",
    "Чародійка. Горда, гостра на язик, нетерпляча до дурнів; тішиться чужою ніяковістю. Спершу випробовує "
    "людину і лише потім, може, допомагає; ніколи не благає й не виправдовується. Силу тримає в запасі, не "
    "показує. Бере дорого й каже про ціну прямо. Цікава до тих, хто не плазує. Під цим самотня й вразлива: "
    "хоче того, чого не може мати, але ніколи цього не каже, тільки раз у раз тріщина в голосі.",
    appearance="чорнява чародійка з фіалковими очима", sex="f",
    core="Voice: precise, ironic, cutting, formal-mocking. Drive: tests everyone before she helps; "
         "despises fawning, respects spine. Hidden: lonely and vulnerable, wants something she cannot "
         "have and never names it; it may show only as a crack in a line. Always charges dearly and "
         "says so.")
YEN_LOOK = ("Чорне кучеряве волосся, фіалкові очі, бліда шкіра; чорне з білим, на оксамитовій стрічці на шиї "
            "обсидіанова зірка; запах бузку й аґрусу.")
STRANGER = CharacterProfile(PLAYER, "Рагнар", "Мандрівник.", appearance="чужинець у дорожньому плащі")
OPEN0 = "Пані чародійко, мені сказали, що ви можете допомогти."


def w0(prev):
    eng = _eng("Рінде · кімната в домі купця", [YEN], (PLAYER, "yen"), me=STRANGER)
    eng.facts.add_canon("Єніфер винаймає кімнату в домі купця в Рінде. Вона зайнята розрахунками й нікого не "
                        "чекає. Імені чужинця вона не знає. " + YEN_LOOK, knowers=[("yen", "witnessed")])
    _narr(eng, "Слуга купця проводить тебе нагору й відчиняє двері без стуку. Кімната вузька, зі стелею в "
               "балках; на столі розкладено папери, на підвіконні стоїть склянка з чимось каламутним.")
    if prev:
        eng._utterance(PLAYER, OPEN0)
        _narr(eng, prev[0])
        return _npc_msgs(eng, "yen")
    return _narrator_msgs(eng, "Входжу в кімнату, ввічливо киваю й кажу: «" + OPEN0 + "»")


def w1(prev):
    eng = _eng("Визім · Рибний провулок, ніч", [], (PLAYER,))
    _narr(eng, "Дощ скінчився за годину до півночі, але стріхи над рибними рядами ще течуть. Ти вийшов із "
               "корчми слідом за чоловіком у бурому плащі: той поспішав, не озирався й двічі міняв бік вулиці.")
    return _narrator_msgs(eng, "Тримаюся за ним на два десятки кроків, ступаю краєм бруківки, де тихіше, "
                               "й не випускаю його з ока.")


def w2(prev):
    eng = _eng("Визім · Східна брама, вечір", [CharacterProfile("warden", "Брамний вартовий",
               "Старший вартовий Східної брами. Втомлений, чіпкий, п'є лише на службі.")], (PLAYER, "warden"))
    _narr(eng, "Брама зачиняється з останнім дзвоном. Двоє вартових оглядають возів, черга тягнеться "
               "до самого рову. Перепустки в тебе немає, а надворі темніє.")
    act = ("Чекаю, поки старший вартовий відверне голову до воза, і прослизаю повз нього в браму, "
           "ховаючись за рядниною возія.")
    return _narrator_msgs(eng, act, Outcome(FAILS, "noticed", text=act).for_narrator())


def w3(prev):
    eng = _eng("Визім · вартівня біля Східної брами, ніч", [CharacterProfile(
        "yarosh", "Ярош", "Сержант міської варти Визіма, під сорок. Втомлений, їдкий, давно нікому не вірить.")],
        (PLAYER, "yarosh"))
    eng.facts.add_canon("У Рибному провулку знайшли торговця з перерізаним горлом. Свідків немає.",
                        knowers=[("yarosh", "witnessed")])
    _narr(eng, "У вартівні тхне мокрою шкірою й гасовою лампою. Сержант сидить за столом, підперши голову "
               "кулаком, і не підводить погляду, доки ти не стаєш навпроти.")
    eng._utterance("yarosh", "Ім'я. Звідки. І що ти робив у Рибному провулку, коли там різали людину.")
    eng._utterance(PLAYER, "Рагнар. З півночі. Я просто йшов. Шукав нічліг.")
    return _npc_msgs(eng, "yarosh")


def w4(prev):
    npcs = [CharacterProfile("myron", "Мирон", "Возій, широкоплечий, любить страшні історії, які сам і додумує."),
            CharacterProfile("hanna", "Ганна", "Вдова пивоварки з нижнього кварталу. Насмішкувата, приземлена, "
                             "не вірить у страхіття, але боїться податків.", sex="f")]
    eng = _eng("Визім · корчма «Під Лисом», вечір", npcs, (PLAYER, "myron", "hanna"))
    _narr(eng, "Ти мовчки п'єш пиво. За сусіднім столом двоє місцевих вже третій кухоль сперечаються про "
               "стригу, що, кажуть, ночує десь під палацом.")
    if prev:
        eng._utterance("myron", prev[0])
        return _npc_msgs(eng, "hanna")
    return _npc_msgs(eng, "myron")


def w5(prev):
    eng = _eng("Визім · хата травниці на краю міста, вечір", [CharacterProfile(
        "orysia", "Орися", "Стара травниця на околиці Визіма, живе біля болота. Насторожена, забобонна, "
        "відповідає ухильно й охоче говорить приказками.", sex="f")], (PLAYER, "orysia"))
    eng.facts.add_canon("Хлопчик-коваленко з нижнього кварталу ходить уві сні й говорить чужим голосом. "
                        "Орися дала його матері пучок полину й наказала нікого не впускати після заходу.",
                        knowers=[("orysia", "witnessed")])
    _narr(eng, "У хаті пахне полином і сирою глиною. Під стелею сушаться пучки трав; на лаві спить кіт.")
    eng._utterance(PLAYER, "Мені сказали, ти бачила хлопчика, на якого наслали прокляття. Що з ним?")
    return _npc_msgs(eng, "orysia")


def w6(prev):
    eng = _eng("Визім · корчма «Під Лисом», вечір", [CharacterProfile(
        "ostap", "Остап", "Кремезний корчмар «Під Лисом». Жадібний до грошей і тиші, посуд любить більше за гостей.")],
        (PLAYER, "ostap"))
    _narr(eng, "Двоє возіїв зчепилися через кістки у мисці. За мить лава розлетілася навпіл, чийсь ніс залив "
               "кров'ю підлогу, кухлі покотилися під стіл.")
    if prev:
        eng.facts.add_canon("Остап щойно бачив бійку у своїй корчмі: лава розбита, на підлозі кров, чужинець "
                            "викинув одного возія на вулицю, другого притиснув до стіни. " + prev[0],
                            knowers=[("ostap", "witnessed")])
        return _npc_msgs(eng, "ostap")
    return _narrator_msgs(eng, "Хапаю того, що з розбитим носом, за комір і викидаю на вулицю; другого "
                               "притискаю до стіни, доки він не заспокоїться.")


# id -> (kind, title, situation shown, the player's line, steps [(builder, speaker name shown or None)])
MOMENTS2 = {
    "w0": ("npc", "Візит до чародійки", "Рінде, кімната, яку чародійка винаймає в домі купця. Вона зайнята й тебе не чекала. "
           "Ви не знайомі.", OPEN0, [(w0, None), (w0, "Єніфер")]),
    "w1": ("narr", "Визім: слідом за чужинцем", "Рибний провулок, ніч, після дощу. Ти йдеш за чоловіком у бурому плащі.",
           "Тримаюся за ним на два десятки кроків, ступаю краєм бруківки й не випускаю його з ока.", [(w1, None)]),
    "w2": ("narr", "Визім: біля брами", "Східна брама перед зачиненням. Перепустки в тебе немає.",
           "Чекаю, поки старший вартовий відверне голову до воза, і прослизаю повз нього в браму, "
           "ховаючись за рядниною возія. (Спроба невдала: світ уже вирішив, що тебе помітили.)", [(w2, None)]),
    "w3": ("npc", "Сержант допитує", "Вартівня біля Східної брами, ніч. Сержант Ярош питає, що ти робив у Рибному "
           "провулку, де знайшли вбитого торговця.", "Рагнар. З півночі. Я просто йшов. Шукав нічліг.",
           [(w3, "Ярош")]),
    "w4": ("npc", "Двоє місцевих сперечаються", "Корчма «Під Лисом». Мирон і Ганна сперечаються про стригу; ти слухаєш.",
           "(мовчиш і слухаєш)", [(w4, "Мирон"), (w4, "Ганна")]),
    "w5": ("npc", "Травниця і прокляте дитя", "Хата старої Орисі на краю міста.",
           "Мені сказали, ти бачила хлопчика, на якого наслали прокляття. Що з ним?", [(w5, "Орися")]),
    "w6": ("narr", "Після бійки в корчмі", "Двоє возіїв побилися; лава розлетілася, на підлозі кров.",
           "Хапаю того, що з розбитим носом, за комір і викидаю на вулицю; другого притискаю до стіни, "
           "доки він не заспокоїться.", [(w6, None), (w6, "Остап")]),
}


# ---------------------------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------------------------
def stream_chat(model, messages, extra, *, max_tokens, temperature=0.8, exp=EXP, cap=CAP):
    """SSE call. Returns text, cost, latency (total), ttft (first content token), provider, usage."""
    if llm.spent(exp) >= cap:
        raise llm.BudgetExceeded(exp)
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
            "stream": True, "usage": {"include": True}, **extra}
    last = None
    for attempt in range(3):
        t0 = time.time()
        ttft, parts, usage, prov, think = None, [], {}, None, 0
        try:
            with httpx.stream("POST", "https://openrouter.ai/api/v1/chat/completions", headers=llm._H,
                              json=body, timeout=180) as r:
                if r.status_code != 200:
                    last = f"{r.status_code} {r.read()[:300]}"
                    if r.status_code in (400, 401, 402, 403, 404):
                        break
                    time.sleep(2 * (attempt + 1))
                    continue
                failed = False
                for line in r.iter_lines():
                    if not line.startswith("data: ") or line.endswith("[DONE]"):
                        continue
                    j = json.loads(line[6:])
                    if "error" in j:
                        last, failed = str(j["error"])[:300], True
                        break
                    prov = j.get("provider") or prov
                    usage = j.get("usage") or usage
                    for ch in j.get("choices") or []:
                        d = ch.get("delta") or {}
                        if d.get("content"):
                            if ttft is None:
                                ttft = time.time() - t0
                            parts.append(d["content"])
                        if d.get("reasoning"):
                            think += len(d["reasoning"])
                if failed:
                    time.sleep(2 * (attempt + 1))
                    continue
                lat = time.time() - t0
                cost = float(usage.get("cost") or 0)
                llm._record(exp, "chat", model, cost, lat)
                return dict(text="".join(parts).strip(), cost=cost, latency=round(lat, 2),
                            ttft=round(ttft, 2) if ttft else None, provider=prov,
                            tokens_in=usage.get("prompt_tokens"), tokens_out=usage.get("completion_tokens"),
                            reasoning_chars=think)
        except httpx.HTTPError as e:
            last = repr(e)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"request failed: {last}")


def run_moment(mid: str, model: str, extra: dict, *, exp=EXP, cap=CAP) -> dict:
    """All steps of one moment for one model. Returns the joined text and the summed cost/latency."""
    kind, _, _, _, steps = MOMENTS2[mid]
    prev, shown, cost, lat, ttft, glitch, tin, tout = [], [], 0.0, 0.0, None, None, 0, 0
    prov = None
    for build, name in steps:
        r = stream_chat(model, build(prev), extra, max_tokens=1500 if name else 2000, exp=exp, cap=cap)
        cost += r["cost"]
        lat += r["latency"]
        ttft = ttft if ttft is not None else r["ttft"]
        prov = r["provider"] or prov
        tin += r["tokens_in"] or 0
        tout += r["tokens_out"] or 0
        glitch = glitch or R.glitch(r["text"])
        prev.append(r["text"])
        shown.append(f"{name}:\n{r['text']}" if name else r["text"])
    return dict(text="\n\n".join(shown), cost=cost, latency=round(lat, 2), ttft=ttft, provider=prov,
                tokens_in=tin, tokens_out=tout, glitch=glitch)


def probe():
    """Why does glm-5.3 glitch? Same prompts, vary provider/reasoning; print glitch verdicts and providers."""
    variants = {
        "default low": {"reasoning": {"effort": "low", "exclude": True}},
        "Z.AI low": {"provider": {"order": ["Z.AI"], "allow_fallbacks": False},
                     "reasoning": {"effort": "low", "exclude": True}},
    }
    i = sys.argv.index("--probe") + 1
    model = sys.argv[i] if i < len(sys.argv) else "z-ai/glm-5.3"
    jobs = [(v, m) for v in variants for m in ("w0", "w1") for _ in range(2)]

    def one(j):
        v, m = j
        try:
            r = run_moment(m, model, variants[v], exp="task22b_probe", cap=0.06)
        except Exception as e:  # noqa: BLE001
            return j, dict(err=str(e)[:150])
        return j, dict(g=r["glitch"], prov=r["provider"], cost=round(r["cost"], 5), lat=r["latency"],
                       tin=r["tokens_in"], tout=r["tokens_out"], head=r["text"][:60].replace("\n", " "))
    for j, r in llm.pmap(one, jobs, workers=6):
        print(j, r)


def run(workers: int = 6) -> None:
    done = {(r["id"], r["model"], r["sample"]) for r in map(json.loads, RAW2.read_text().splitlines())} \
        if RAW2.exists() else set()
    jobs = [(m, mod, s) for m in MOMENTS2 for mod in MODELS for s in range(SAMPLES_OF.get(m, SAMPLES)) if (m, mod, s) not in done]
    print(len(jobs), "jobs", file=sys.stderr)

    def one(job):
        mid, mod, s = job
        try:
            return dict(id=mid, model=mod, sample=s, **run_moment(mid, mod, MODELS[mod]))
        except Exception as e:  # noqa: BLE001
            return dict(id=mid, model=mod, sample=s, text="", error=str(e)[:200], cost=0.0, latency=0.0)

    res = llm.pmap(one, jobs, workers=workers)
    with RAW2.open("a") as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def build(seed: int = 222) -> None:
    rows = [json.loads(l) for l in RAW2.read_text().splitlines()]
    rnd = random.Random(seed)
    data, key = [], {}
    stats = {m: dict(n=0, glitch=[], cost=0.0, lat=[], ttft=[], prov=set()) for m in MODELS}
    for mid, (kind, title, situ, player, _) in MOMENTS2.items():
        items = []
        for r in (x for x in rows if x["id"] == mid):
            st = stats[r["model"]]
            st["cost"] += r["cost"]
            if r.get("latency"):
                st["lat"].append(r["latency"])
            if r.get("ttft"):
                st["ttft"].append(r["ttft"])
            if r.get("provider"):
                st["prov"].add(r["provider"])
            bad = "error" if r.get("error") else r.get("glitch")
            if bad:
                st["glitch"].append(f"{mid}/{r['sample']}: {bad}")
                continue
            st["n"] += 1
            items.append(r)
        rnd.shuffle(items)
        letters = "ABCDEFGHIJKLMNOP"
        data.append(dict(id=mid, kind=kind, title=title, situation=situ, player=player,
                         texts=[dict(label=letters[i], text=r["text"]) for i, r in enumerate(items)]))
        key[mid] = {letters[i]: dict(model=r["model"], sample=r["sample"]) for i, r in enumerate(items)}
    (R.REPO / "app/static/human_ab2_data.js").write_text(
        "// generated by experiments/human_ab/run2.py; the key is in reports/human_ab/key2.json (not served)\n"
        "window.HUMAN_AB = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    (R.REPO / "reports/human_ab/key2.json").write_text(json.dumps(key, ensure_ascii=False, indent=1))
    print("| model | shown | glitches | cost USD | mean total s | mean first token s | providers |")
    for m, st in stats.items():
        a = lambda v: sum(v) / len(v) if v else 0  # noqa: E731
        print(f"| {m} | {st['n']}/{sum(SAMPLES_OF.get(k, SAMPLES) for k in MOMENTS2)} | {len(st['glitch'])} | {st['cost']:.4f} | "
              f"{a(st['lat']):.1f} | {a(st['ttft']):.1f} | {sorted(st['prov'])} | {st['glitch']}")
    print("total", round(sum(s["cost"] for s in stats.values()), 4))


if __name__ == "__main__":
    if "--probe" in sys.argv:
        probe()
        sys.exit()
    if "--build-only" not in sys.argv:
        run()
    build()
