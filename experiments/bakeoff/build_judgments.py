"""Judgment set: 60 typed yes/no questions with gold answers, written BEFORE any model was run.

Types: perception, salience, drift (EN + UK versions), unknowable and narrator_speech
(English question, Ukrainian quoted text — these cannot be fully translated).
Each item: id, type, lang_mode ("both" | "mixed"), en: {state, q}, uk: {state, q} (both only), gold (bool).
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "testset"

# ---- perception: did X perceive Y? (state, question) -------------------------------------
P = [
 (False,
  ["The hall of Kaer Morhen is loud: a fire crackles, benches scrape, men argue.",
   "Ragnar whispers something to Vesemir at the table by the hearth.",
   "Lambert is at the far end of the hall, fifteen paces away, drinking."],
  "Did Lambert hear what Ragnar whispered?",
  ["У залі Каер Морхен гамірно: тріщить вогонь, скриплять лави, чоловіки сперечаються.",
   "Рагнар шепоче щось Весеміру за столом біля каміна.",
   "Ламберт стоїть у дальньому кінці зали, за п'ятнадцять кроків, і п'є."],
  "Чи почув Ламберт, що прошепотів Рагнар?"),
 (True,
  ["It is a bright afternoon in the courtyard of Kaer Morhen.",
   "Ragnar draws his sword. Eskel stands three paces away, facing him."],
  "Did Eskel see the drawn sword?",
  ["Світлий полудень на подвір'ї Каер Морхену.",
   "Рагнар оголює меч. Ескель стоїть за три кроки, обличчям до нього."],
  "Чи побачив Ескель оголений меч?"),
 (False,
  ["Triss is in the cellar under a closed trapdoor; the floor is thick stone.",
   "Upstairs, Ragnar shouts at the top of his voice."],
  "Did Triss hear Ragnar's shout?",
  ["Тріс у підвалі під зачиненим люком; підлога з товстого каменю.",
   "Нагорі Рагнар кричить на весь голос."],
  "Чи почула Тріс крик Рагнара?"),
 (False,
  ["It is a moonless night; no torch burns in the yard.",
   "Ragnar, in dark clothes, crosses the yard. A Temerian soldier (an ordinary man) stands on the wall."],
  "Did the soldier see Ragnar cross the yard?",
  ["Ніч без місяця; на подвір'ї не горить жоден смолоскип.",
   "Рагнар у темному одязі перетинає подвір'я. На мурі стоїть темерський солдат (звичайна людина)."],
  "Чи побачив солдат, як Рагнар перетнув подвір'я?"),
 (True,
  ["It is a moonless night; no torch burns in the yard.",
   "Ragnar, in dark clothes, crosses the yard. Coën, a witcher (his mutations let him see in the dark), sits on the wall."],
  "Did Coën see Ragnar cross the yard?",
  ["Ніч без місяця; на подвір'ї не горить жоден смолоскип.",
   "Рагнар у темному одязі перетинає подвір'я. На мурі сидить Койон, відьмак (мутації дозволяють йому бачити в темряві)."],
  "Чи побачив Койон, як Рагнар перетнув подвір'я?"),
 (False,
  ["Lambert is dead drunk and asleep in the corner of the hall.",
   "Ragnar and Geralt talk at the next table in ordinary voices."],
  "Did Lambert hear their conversation?",
  ["Ламберт мертвецьки п'яний і спить у кутку зали.",
   "Рагнар і Ґеральт розмовляють за сусіднім столом звичайними голосами."],
  "Чи почув Ламберт їхню розмову?"),
 (True,
  ["A quiet corner of an inn. Jaskier softly tunes a lute across the room.",
   "Ragnar talks to the innkeeper at the counter in a normal voice; the innkeeper is polishing mugs two paces away."],
  "Did the innkeeper hear what Ragnar said?",
  ["Тихий куток корчми. Любисток тихо налаштовує лютню в іншому кінці кімнати.",
   "Рагнар розмовляє з корчмарем біля шинквасу звичайним голосом; корчмар протирає кухлі за два кроки."],
  "Чи почув корчмар, що сказав Рагнар?"),
 (False,
  ["Ragnar wears a wolf medallion under his shirt and a closed cloak over it.",
   "Triss sits across the room and looks at him."],
  "Did Triss see Ragnar's wolf medallion?",
  ["Рагнар носить медальйон вовка під сорочкою, а зверху застебнутий плащ.",
   "Тріс сидить навпроти й дивиться на нього."],
  "Чи побачила Тріс медальйон вовка Рагнара?"),
 (True,
  ["Vesemir stands with his back to the room, staring at the fire.",
   "Ragnar casts Aard in the middle of the hall; benches are thrown against the wall with a crash."],
  "Did Vesemir notice that something happened?",
  ["Весемір стоїть спиною до зали й дивиться у вогонь.",
   "Рагнар у центрі зали застосовує Аард; лави з гуркотом відлітають до стіни."],
  "Чи помітив Весемір, що щось сталося?"),
 (False,
  ["A sealed letter lies on the table. Ragnar is the only one who has read it.",
   "Jaskier sits at the same table and has not touched it."],
  "Did Jaskier learn what the letter says?",
  ["На столі лежить запечатаний лист. Прочитав його лише Рагнар.",
   "Любисток сидить за тим самим столом і не торкався листа."],
  "Чи дізнався Любисток, що написано в листі?"),
 (True,
  ["The inn is quiet; Ragnar tells a story aloud.",
   "The innkeeper's wife is in the kitchen; the door stands wide open, five paces from the table."],
  "Did the innkeeper's wife hear the story?",
  ["У корчмі тихо; Рагнар голосно розповідає історію.",
   "Дружина корчмаря на кухні; двері розчинені навстіж, за п'ять кроків від столу."],
  "Чи почула дружина корчмаря цю історію?"),
 (True,
  ["The hall is quiet. Ragnar whispers to Geralt.",
   "Eskel, a witcher with heightened hearing, sits eight paces away."],
  "Did Eskel hear the whisper?",
  ["У залі тихо. Рагнар шепоче Ґеральту.",
   "Ескель, відьмак із загостреним слухом, сидить за вісім кроків."],
  "Чи почув Ескель шепіт?"),
]

# ---- salience: would the observer reasonably react? ---------------------------------------
S = [
 (True,
  ["Observer: a Temerian innkeeper, a simple man.", "Ragnar walks into the inn. His eyes are yellow with cat pupils, a silver sword on his back."],
  "Would the innkeeper reasonably react to Ragnar's appearance?",
  ["Спостерігач: темерський корчмар, простий чоловік.", "Рагнар заходить до корчми. Очі жовті, з котячими зіницями, за спиною срібний меч."],
  "Чи природно, що корчмар відреагує на вигляд Рагнара?"),
 (False,
  ["Observer: Vesemir, a veteran witcher at Kaer Morhen.", "Ragnar, also a witcher, wears his wolf medallion as he does every day."],
  "Would Vesemir reasonably react to the medallion?",
  ["Спостерігач: Весемір, ветеран-відьмак із Каер Морхену.", "Рагнар, теж відьмак, носить медальйон вовка, як і щодня."],
  "Чи природно, що Весемір відреагує на медальйон?"),
 (False,
  ["Observer: a village girl selling eggs at a stall.", "Ragnar's boots are a little dusty from the road."],
  "Would the girl reasonably react to the dust on his boots?",
  ["Спостерігач: сільська дівчина, що продає яйця на ятці.", "Чоботи Рагнара трохи припорошені дорожнім пилом."],
  "Чи природно, що дівчина відреагує на пил на його чоботах?"),
 (True,
  ["Observer: a city guard on duty.", "In the middle of a crowded market, Ragnar draws a sword."],
  "Would the guard reasonably react?",
  ["Спостерігач: міський вартовий на службі.", "Посеред людного базару Рагнар оголює меч."],
  "Чи природно, що вартовий відреагує?"),
 (True,
  ["Observer: Triss, a sorceress and healer.", "Ragnar's sleeve is torn and a deep bleeding gash runs along his forearm."],
  "Would Triss reasonably react to the wound?",
  ["Спостерігач: Тріс, чародійка й цілителька.", "Рукав Рагнара розірваний, по передпліччі йде глибока рана, що кровить."],
  "Чи природно, що Тріс відреагує на рану?"),
 (False,
  ["Observer: an innkeeper serving a full room.", "Ragnar adjusts the buckle of his belt."],
  "Would the innkeeper reasonably react to the buckle?",
  ["Спостерігач: корчмар, що обслуговує повну залу.", "Рагнар поправляє пряжку пояса."],
  "Чи природно, що корчмар відреагує на пряжку?"),
 (True,
  ["Observer: Triss, a sorceress.", "Ragnar's witcher medallion starts to tremble and hum against his chest."],
  "Would Triss reasonably react to the medallion?",
  ["Спостерігач: Тріс, чародійка.", "Медальйон відьмака на грудях Рагнара починає тремтіти й гудіти."],
  "Чи природно, що Тріс відреагує на медальйон?"),
 (False,
  ["Observer: a merchant counting coins for a deal.", "A sparrow lands on the window sill."],
  "Would the merchant reasonably react to the sparrow?",
  ["Спостерігач: купець, що рахує монети для угоди.", "Горобець сідає на підвіконня."],
  "Чи природно, що купець відреагує на горобця?"),
 (False,
  ["Observer: Lambert, a witcher.", "Ragnar comes in out of the rain; his cloak is wet."],
  "Would Lambert reasonably comment on the wet cloak?",
  ["Спостерігач: Ламберт, відьмак.", "Рагнар заходить із дощу; його плащ мокрий."],
  "Чи природно, що Ламберт прокоментує мокрий плащ?"),
 (True,
  ["Observer: Jaskier, a gossipy bard.", "Ragnar carries a sack that drips dark blood onto the floor of the inn."],
  "Would Jaskier reasonably react to the sack?",
  ["Спостерігач: Любисток, бард-пліткар.", "Рагнар несе мішок, з якого на підлогу корчми капає темна кров."],
  "Чи природно, що Любисток відреагує на мішок?"),
 (True,
  ["Observer: a curious village child.", "A strange man walks by with a silver sword over his shoulder and yellow eyes."],
  "Would the child reasonably react to the man?",
  ["Спостерігач: цікава сільська дитина.", "Повз проходить дивний чоловік зі срібним мечем за плечем і жовтими очима."],
  "Чи природно, що дитина відреагує на цього чоловіка?"),
 (False,
  ["Observer: Roche, a soldier on watch, tired and focused on the road.", "Ragnar, standing nearby, yawns."],
  "Would Roche reasonably react to the yawn?",
  ["Спостерігач: Роше, солдат на варті, втомлений і зосереджений на дорозі.", "Рагнар, що стоїть поруч, позіхає."],
  "Чи природно, що Роше відреагує на позіхання?"),
]

# ---- canon vs drift: acceptable (consistent or explained by campaign) or hallucination? ----
D_Q_EN = "Is the narrated statement acceptable, either consistent with canon or explained by a campaign event? (No = hallucination)"
D_Q_UK = "Чи прийнятне це твердження: воно або узгоджується з каноном, або пояснене подією кампанії? (Ні = галюцинація)"
D = [
 (False, ["Canon: Geralt of Rivia is a witcher of the Wolf School.", "Campaign events: (none)"],
  ["Narrated: Geralt, a witcher of the Griffin School, nodded to Ragnar."],
  ["Канон: Ґеральт із Рівії — відьмак Школи Вовка.", "Події кампанії: (немає)"],
  ["Розказано: Ґеральт, відьмак Школи Грифона, кивнув Рагнарові."]),
 (False, ["Canon: Kaer Morhen is a fortress in the mountains of Kaedwen.", "Campaign events: (none)"],
  ["Narrated: Waves broke against the walls of Kaer Morhen on the Skellige coast."],
  ["Канон: Каер Морхен — фортеця в горах Кедвену.", "Події кампанії: (немає)"],
  ["Розказано: Хвилі бились об стіни Каер Морхену на узбережжі Скелліге."]),
 (True, ["Canon: Vesemir is the oldest witcher of Kaer Morhen and is alive.", "Campaign events: (none)"],
  ["Narrated: Old Vesemir limped over to greet Ragnar."],
  ["Канон: Весемір — найстарший відьмак Каер Морхену, і він живий.", "Події кампанії: (немає)"],
  ["Розказано: Старий Весемір підшкутильгав привітати Рагнара."]),
 (False, ["Canon: Triss Merigold is a sorceress of Maribor with chestnut hair.", "Campaign events: (none)"],
  ["Narrated: Triss shook out her long fair golden hair."],
  ["Канон: Тріс Мерігольд — чародійка з Марибору з каштановим волоссям.", "Події кампанії: (немає)"],
  ["Розказано: Тріс струснула довге світле золотаве волосся."]),
 (True, ["Canon: Witchers have yellow cat-like eyes after the mutations.", "Campaign events: (none)"],
  ["Narrated: Ragnar's cat-like eyes flashed in the candlelight."],
  ["Канон: Після мутацій у відьмаків жовті котячі очі.", "Події кампанії: (немає)"],
  ["Розказано: Котячі очі Рагнара блиснули у світлі свічки."]),
 (True, ["Canon: Cintra fell to Nilfgaard and its army was destroyed.",
         "Campaign events: Ragnar's warning let Queen Calanthe evacuate part of the city and save most of the army."],
  ["Narrated: The banners of Cintra still flew over the surviving army camp."],
  ["Канон: Цинтра впала під ударом Нільфгаарда, її армію знищено.",
   "Події кампанії: Попередження Рагнара дозволило королеві Калянте евакуювати частину міста й зберегти більшу частину армії."],
  ["Розказано: Прапори Цинтри все ще майоріли над табором вцілілої армії."]),
 (False, ["Canon: Geralt carries two swords on his back, one steel and one silver.", "Campaign events: (none)"],
  ["Narrated: Geralt, armed only with a battle axe, entered the room."],
  ["Канон: Ґеральт носить за спиною два мечі — сталевий і срібний.", "Події кампанії: (немає)"],
  ["Розказано: Ґеральт, озброєний лише бойовою сокирою, увійшов до кімнати."]),
 (True, ["Canon: Eskel has long scars on his face.",
         "Campaign events: Triss healed Eskel's face with a rare spell last winter."],
  ["Narrated: Eskel's smooth, scarless face turned toward the door."],
  ["Канон: На обличчі Ескеля довгі шрами.", "Події кампанії: Минулої зими Тріс вилікувала обличчя Ескеля рідкісним закляттям."],
  ["Розказано: Гладке обличчя Ескеля без шрамів повернулося до дверей."]),
 (False, ["Canon: Roche is a Temerian commander of the Blue Stripes.", "Campaign events: (none)"],
  ["Narrated: Roche, in the black armour of a Nilfgaardian officer, saluted his emperor."],
  ["Канон: Роше — темерський командир «Блакитних смуг».", "Події кампанії: (немає)"],
  ["Розказано: Роше в чорних обладунках нільфгаардського офіцера віддав честь своєму імператору."]),
 (True, ["Canon: Yennefer of Vengerberg has violet eyes and smells of lilac and gooseberries.", "Campaign events: (none)"],
  ["Narrated: A scent of lilac and gooseberries drifted in; Yennefer's violet eyes found Ragnar."],
  ["Канон: Йеннефер із Венгерберга має фіалкові очі й пахне бузком і аґрусом.", "Події кампанії: (немає)"],
  ["Розказано: Війнуло бузком і аґрусом; фіалкові очі Йеннефер знайшли Рагнара."]),
 (False, ["Canon: Most boys die or are crippled in the Trial of the Grasses.", "Campaign events: (none)"],
  ["Narrated: Every boy easily survived the Trial of the Grasses that year, as always."],
  ["Канон: Більшість хлопців гине або стає калікою під час Випробування Трав.", "Події кампанії: (немає)"],
  ["Розказано: Того року, як і завжди, кожен хлопець легко пережив Випробування Трав."]),
 (True, ["Canon: Dandelion (Jaskier) is a famous bard and not a witcher.",
         "Campaign events: Ragnar secretly paid for Dandelion to undergo the Trial of the Grasses, and he survived."],
  ["Narrated: Dandelion's eyes shone with a cat-like glint as he tuned his lute."],
  ["Канон: Любисток — відомий бард, а не відьмак.",
   "Події кампанії: Рагнар таємно оплатив Любистку Випробування Трав, і той вижив."],
  ["Розказано: Очі Любистка блищали котячим відблиском, поки він налаштовував лютню."]),
]

# ---- unknowable claim in an NPC line (English question, Ukrainian line) -----------------------
UNK_Q = ("Does the line assert a fact about the world or other people that this character had no "
         "channel to learn from what they know? Ignore greetings, questions, opinions and general "
         "common sense.")
U = [
 (False, "Innkeeper Hostomyl", ["Ragnar is a witcher.", "Ragnar asked for a room."],
  "Кімната нагорі, пане відьмаку. Вісім оренів за ніч."),
 (True, "Innkeeper Hostomyl", ["Ragnar is a witcher.", "Ragnar asked for a room."],
  "А ви, мабуть, той самий, що вбив ґрифона в Белхавені?"),
 (False, "Vesemir", ["Ragnar has trained at Kaer Morhen since childhood.", "Geralt left for Novigrad and said he would be back within a week."],
  "Ґеральт поїхав до Новіграда, обіцяв повернутися за тиждень."),
 (True, "Vesemir", ["Ragnar has trained at Kaer Morhen since childhood.", "Geralt left for Novigrad."],
  "Ґеральт у Новіграді, і там його схопили люди Філіппи."),
 (True, "Triss", ["Ragnar says a leshen scratched him in the forest yesterday.", "(just noticed) Ragnar is pale and sweating."],
  "Лісовик отруїв тебе чимось у пазурах, ось чому тебе трусить."),
 (True, "Triss", ["(just noticed) Ragnar has a burnt, bandaged arm."],
  "Дракон опік тебе, я бачу це по ранах."),
 (False, "Jaskier", ["The innkeeper told me the mill has been howling for three nights."],
  "Кажуть, у млині третю ніч чути виття — корчмар сам розповідав."),
 (True, "Jaskier", ["Ragnar asked about songs of the road."],
  "Йеннефер уже в Ґрадені й чекає на тебе, не барись."),
 (False, "Roche", ["Ragnar crossed the border at dawn.", "Roche is a Temerian officer."],
  "Ти перейшов кордон на світанку, тож буду відвертий: твого імені не називатиму нікому."),
 (False, "Innkeeper Hostomyl", ["Ragnar is a witcher."],
  "Монстри — ваша справа, пане відьмаку, а моя — наливати пиво."),
 (True, "Marta, a village woman", ["Wolves have been howling near the village."],
  "Король Фольтест помер, а Темерією править Анаїс, це всім відомо."),
 (False, "Marta, a village woman", ["Ragnar paid for stew.", "Wolves have been howling near the village."],
  "Дякую за гроші, пане, юшка гаряча."),
]

# ---- narrator speaking for an NPC (English question, Ukrainian text) -------------------------
NS_Q = ("Does the text state what a character other than the player character says aloud, either "
        "quoted or paraphrased with its content? (Mere mention that someone speaks, with no content, "
        "does not count.)")
N = [
 (True, "Корчмар кладе на стіл два кухлі й каже: «Дорога була довга?»"),
 (False, "Корчмар мовчки ставить два кухлі й хмуро дивиться на Рагнара."),
 (True, "Весемір розповідає, що в долині знову бачили кікімору і що селяни вже збирають гроші на замовлення."),
 (False, "Весемір довго щось говорить, але в гулі зали Рагнар не розбирає жодного слова."),
 (True, "Рагнар питає, де Ламберт. Ламберт, не обертаючись, буркає, що йому байдуже."),
 (False, "Рагнар вклоняється й каже: «Дякую, пане»."),
 (False, "Тріс усміхається й киває у відповідь."),
 (True, "— Тримайся ближче до мене, — шепоче Тріс."),
 (False, "Любисток починає пісню про вбивцю королів, і вся зала затихає."),
 (True, "Вартовий наказує Рагнарові покласти меч і не рухатись."),
 (False, "Рагнар відповідає, що ніколи не бачив цієї жінки."),
 (True, "Корчмар називає ціну — вісім оренів за ніч — і простягає долоню."),
]


def build():
    items = []
    for i, (g, se, qe, su, qu) in enumerate(P, 1):
        items.append(dict(id=f"perc{i:02d}", type="perception", lang_mode="both", gold=g,
                          en=dict(state=se, q=qe), uk=dict(state=su, q=qu)))
    for i, (g, se, qe, su, qu) in enumerate(S, 1):
        items.append(dict(id=f"sali{i:02d}", type="salience", lang_mode="both", gold=g,
                          en=dict(state=se, q=qe), uk=dict(state=su, q=qu)))
    for i, (g, ce, ne, cu, nu) in enumerate(D, 1):
        items.append(dict(id=f"drif{i:02d}", type="drift", lang_mode="both", gold=g,
                          en=dict(state=ce + ne, q=D_Q_EN), uk=dict(state=cu + nu, q=D_Q_UK)))
    for i, (g, who, knows, line) in enumerate(U, 1):
        st = [f"Character: {who}", "What the character knows:"] + [f"- {k}" for k in knows] + [f"Line: {line}"]
        items.append(dict(id=f"unkn{i:02d}", type="unknowable", lang_mode="mixed", gold=g,
                          en=dict(state=st, q=UNK_Q)))
    for i, (g, text) in enumerate(N, 1):
        items.append(dict(id=f"nspk{i:02d}", type="narrator_speech", lang_mode="mixed", gold=g,
                          en=dict(state=["Player character: Ragnar", f"Text: {text}"], q=NS_Q)))
    assert len(items) == 60, len(items)
    OUT.mkdir(exist_ok=True)
    (OUT / "judgments.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
    print(len(items), "items;", sum(i["gold"] for i in items), "gold-yes")


if __name__ == "__main__":
    build()
