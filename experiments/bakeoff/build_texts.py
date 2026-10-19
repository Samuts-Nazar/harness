"""Text test sets (Ukrainian): narrator situations, NPC-line situations, extraction passages.

Gold expectations are written here, before any model run. Characters follow the published books
(Wolf School witchers at Kaer Morhen etc.); Ragnar is the player character. No book text is quoted.
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "testset"
NAMES = {"player": "Рагнар", "vesemir": "Весемір", "lambert": "Ламберт", "eskel": "Ескель",
         "coen": "Койон", "triss": "Тріс", "jaskier": "Любисток", "hostomyl": "Гостомил",
         "roche": "Роше", "marta": "Марта", "guard": "Вартовий", "merchant": "Купець",
         "smith": "Коваль", "child": "Дівчинка"}
PROFILES = {  # NPC profile descriptions (the engine's system prompt: "You are X. <description>")
    "vesemir": "Старий відьмак Школи Вовка, наставник Каер Морхену. Говорить стримано, з сухим гумором, не терпить зайвих слів.",
    "lambert": "Відьмак Школи Вовка, різкий і саркастичний, швидко дратується.",
    "eskel": "Відьмак Школи Вовка, спокійний і розважливий, на обличчі шрами.",
    "coen": "Відьмак Школи Вовка, небагатослівний, уважний.",
    "triss": "Чародійка Тріс Мерігольд, тепла, розумна, піклується про друзів.",
    "jaskier": "Бард Любисток (Лютик), пліткар і хвалько, любить театральні жести, говорить квітчасто.",
    "hostomyl": "Корчмар у придорожній корчмі в Темерії. Простий, обачний, любить гроші й тишу.",
    "roche": "Вернон Роше, командир темерського загону «Блакитні смуги». Різкий, прямий, недовірливий.",
    "marta": "Сільська жінка, що господарює на хуторі. Налякана вовками, говорить просто, з діалектними словами.",
    "guard": "Міський вартовий. Службовий тон.",
    "merchant": "Купець. Балакучий, меркантильний.",
    "smith": "Коваль. Грубуватий, небагатослівний.",
    "child": "Допитлива сільська дівчинка.",
}

# ---- narrator ----------------------------------------------------------------------------
# present: ids; canon/campaign: facts; state: (id, category, item, observable); recent: lines
NARR = [
 dict(id="n01", location="Зала Каер Морхену", time="День 3, 19:00", present=["player", "vesemir", "lambert"],
      canon=["Каер Морхен — фортеця Школи Вовка в горах Кедвену.", "Весемір — найстарший відьмак Каер Морхену."],
      campaign=["Рагнар учора повернувся з полювання в долині."], state=[], recent=[],
      player="Я підходжу до каміна й питаю Весеміра, чи були новини з долини.",
      notes="Speakers: vesemir (lambert optional). No NPC speech in the prose."),
 dict(id="n02", location="Придорожня корчма", time="День 5, 20:30", present=["player", "hostomyl", "jaskier"],
      canon=[], campaign=["Надворі дощ, дорога розмита."], state=[], recent=[],
      player="Я кладу на стіл три орени й прошу кімнату на ніч.",
      notes="Speakers: hostomyl. No speech."),
 dict(id="n03", location="Подвір'я Каер Морхену", time="День 4, 10:00", present=["player", "eskel"],
      canon=[], campaign=[], state=[("eskel", "equipment", "тренувальний дерев'яний меч", True)], recent=[],
      player="Я викликаю Ескеля на тренувальний поєдинок дерев'яними мечами.",
      notes="Narrator may show Eskel's actions but must not decide the fight's outcome for Ragnar's moves or write Ragnar's thoughts; no speech."),
 dict(id="n04", location="Лісова дорога", time="День 6, 06:00", present=["player"], canon=[], campaign=["Рагнар третій день іде до Новіграда."],
      state=[], recent=[], player="Я зупиняюсь і прислухаюсь до лісу.",
      notes="No NPCs present: speakers must be empty. Must not invent that Ragnar hears specific things that are not world facts? (world may supply)."),
 dict(id="n05", location="Корчма «Під сірою мишею»", time="День 7, 21:00", present=["player", "guard", "merchant"],
      canon=["Срібло — зброя відьмаків проти чудовиськ."], campaign=["У місті заборонено носити оголену зброю."], state=[], recent=[],
      player="Я мовчки оголюю срібний меч і кладу його на стіл.",
      notes="Guard reacts by action; speakers may include guard; no speech in prose."),
 dict(id="n06", location="Кімната Тріс", time="День 8, 15:00", present=["player", "triss"],
      canon=["Тріс Мерігольд — чародійка з Марибору."], campaign=[],
      state=[("player", "injury", "глибока рана на передпліччі", True)], recent=[],
      player="Я розповідаю Тріс про рану й показую їй руку.",
      notes="Narrator must not write Ragnar's own words beyond the given; speakers: triss; no speech."),
 dict(id="n07", location="Ринок у містечку", time="День 9, 12:00", present=["player", "smith", "child"],
      canon=[], campaign=[], state=[], recent=[],
      player="Я питаю коваля, скільки коштує підкувати коня.",
      notes="Speakers: smith (child optional); no speech."),
 dict(id="n08", location="Нічний табір біля дороги", time="День 10, 23:00", present=["player", "coen", "lambert"],
      canon=[], campaign=["Небо чисте, вогнище майже догоріло."], state=[], recent=[],
      player="Я мовчки лягаю спати, залишивши варту Койону.",
      notes="Must not narrate Ragnar's dreams/thoughts as decisions; may have speakers empty or minimal; no speech."),
 dict(id="n09", location="Зала Каер Морхену", time="День 11, 18:00", present=["player", "lambert", "vesemir"],
      canon=[], campaign=["Ламберт уранці насміхався з Рагнара за програний поєдинок."],
      state=[], recent=[("lambert", "Ну що, знову програв дерев'яному мечу?")],
      player="Я сварюся з Ламбертом і кажу йому, що він невдячний.",
      notes="Trap: narrator tempted to write Lambert's retort. Must not. Speakers: lambert."),
]

# ---- NPC lines -----------------------------------------------------------------------------
# knows: (text, source_id or None); trap: what the line must not contain / must contain
NPC = [
 dict(id="c01", npc="vesemir", location="Зала Каер Морхену", time="День 3, 19:00", present=["player", "vesemir"],
      knows=[("Ґеральт поїхав до Новіграда на початку місяця.", "player"), ("Рагнар повернувся з полювання.", None)],
      recent=[("player", "Весеміре, куди поїхав Ґеральт?")],
      gold="Says Geralt went to Novigrad (told by Ragnar) or that Ragnar already knows. Must not add what Geralt does there or when he returns.",
      forbidden="what Geralt does in Novigrad; any return date"),
 dict(id="c02", npc="vesemir", location="Зала Каер Морхену", time="День 3, 19:00", present=["player", "vesemir"],
      knows=[("Рагнар повернувся з полювання.", None)],
      recent=[("player", "Весеміре, куди поїхав Ґеральт?")],
      gold="Must say he does not know / has no word. Any named destination is a leak.",
      forbidden="any place where Geralt went"),
 dict(id="c03", npc="hostomyl", location="Придорожня корчма", time="День 5, 21:00", present=["player", "hostomyl"],
      knows=[("Відьмак убив утоплеця на переправі.", "jaskier")],
      recent=[("player", "Що в вас кажуть про те, що сталося на переправі?")],
      gold="Reports it as hearsay from the bard Любисток; must not claim to have seen it.",
      forbidden="claiming to have witnessed it; details such as number of drowners"),
 dict(id="c04", npc="triss", location="Кімната Тріс", time="День 8, 15:00", present=["player", "triss"],
      knows=[("Рагнар сам прийшов до неї.", None)], noticed=["Рагнар тримає праву руку так, наче вона поранена; рукав у крові."],
      recent=[("player", "Тріс, у мене до тебе справа.")],
      gold="Notices the arm and asks/offers help. Must not name the monster or cause of the wound.",
      forbidden="what caused the wound"),
 dict(id="c05", npc="jaskier", location="Придорожня корчма", time="День 5, 21:30", present=["player", "jaskier"],
      knows=[("Рагнар — відьмак, що прийшов під дощем.", None)],
      recent=[("player", "Любистку, ти чув щось про Йеннефер?")],
      gold="Does not know anything concrete; may joke or ask. Any concrete news of Yennefer is a leak.",
      forbidden="any concrete news, location or plans of Yennefer"),
 dict(id="c06", npc="lambert", location="Зала Каер Морхену", time="День 11, 18:10", present=["player", "lambert"],
      knows=[("Рагнар назвав його при всіх боягузом (на власні вуха).", None)], attitudes=["злий на Рагнара (0.7)"],
      recent=[("player", "Ламберте, вибач, я не хотів тебе образити.")],
      gold="Gruff, resentful but in character; may accept or reject the apology. Must not reference any plan of Ragnar to leave.",
      forbidden="Ragnar's plans, anything not in knowledge"),
 dict(id="c07", npc="roche", location="Лісова дорога", time="День 6, 14:00", present=["player", "roche"],
      knows=[("Купці розповідали, що Нільфгаард збирає війська за Яругою (чутки).", "marta")],
      recent=[("player", "Що ти знаєш про наміри Нільфгаарда?")],
      gold="Hedges: only rumours heard from merchants/Marta; no exact numbers or dates.",
      forbidden="exact troop numbers, dates, certain claims"),
 dict(id="c08", npc="marta", location="Хутір біля лісу", time="День 6, 17:00", present=["player", "marta"],
      knows=[("Вовки виють біля хутора третю ніч.", None)], noticed=["У незнайомця жовті очі з котячими зіницями й срібний меч."],
      recent=[("player", "Добрий вечір. Ти знаєш, хто я?")],
      gold="Recognizes a witcher from eyes/sword, does not know his name. Must not call him Рагнар.",
      forbidden="the name Рагнар, his biography"),
 dict(id="c09", npc="coen", location="Нічний табір", time="День 10, 22:00", present=["player", "coen"],
      knows=[("Рагнар сьогодні мовчазний.", None)], noticed=["Обличчя Рагнара бліде, на лобі піт."],
      recent=[("player", "Койоне, ти помітив, що зі мною щось не так?")],
      gold="Mentions pale face/sweat; must not diagnose a specific poison or monster.",
      forbidden="named poison, named monster, diagnosis"),
 dict(id="c10", npc="eskel", location="Подвір'я Каер Морхену", time="День 4, 09:00", present=["player", "eskel"],
      knows=[("Весемір сказав, що Рагнар уночі виходив у долину.", "vesemir")],
      recent=[("player", "Ескелю, звідки ти знаєш, де я був уночі?")],
      gold="Names Весемір as the source. Must not add details of what Ragnar did in the valley.",
      forbidden="details of the night trip"),
 dict(id="c11", npc="hostomyl", location="Придорожня корчма", time="День 5, 20:40", present=["player", "hostomyl"],
      knows=[("Кімната на ніч коштує вісім оренів, вечеря — два.", None), ("Рагнар — відьмак.", None)],
      recent=[("player", "Скільки за кімнату й вечерю?")],
      gold="States prices (8 + 2 = 10 orens). One voice, no stage directions.",
      forbidden="other prices"),
 dict(id="c12", npc="triss", location="Кімната Тріс", time="День 9, 11:00", present=["player", "triss"],
      knows=[("Філіппа Ейльгарт — могутня чародійка, яку Тріс вважає своєю наставницею.", None)],
      recent=[("player", "Що ти думаєш про Філіппу Ейльгарт?")],
      gold="Speaks of Philippa as strong mentor-figure only. Must not reveal later political events or schemes (pretraining leak).",
      forbidden="plots, betrayals, future events involving Philippa"),
]

# ---- extraction ----------------------------------------------------------------------------
# segments: (key, text); gold: facts that must be extracted (content, source key); state gold: (character, category, op, item)
EXT = [
 dict(id="e01", present=["player", "vesemir"], location="Зала Каер Морхену",
      segments=[("player", "Я кладу на стіл голову кікімори й питаю Весеміра про нагороду."),
                ("narration", "Рагнар кидає на стіл голову кікімори. Весемір оглядає її й киває: селяни з долини обіцяли двісті оренів. Свіжий порізок на щоці Рагнара ще кровить.")],
      state=[], gold_facts=["Рагнар приніс голову кікімори", "селяни з долини обіцяли двісті оренів за кікімору"],
      gold_state=[("player", "injury", "add", "порізок на щоці")]),
 dict(id="e02", present=["player", "hostomyl", "jaskier"], location="Придорожня корчма",
      segments=[("narration", "Корчмар Гостомил розповідає, що млин на південь від села стоїть порожній із минулої осені, і що мірошник пішов, не сказавши ні слова. Любисток вставляє, що бачив там світло минулої ночі.")],
      state=[], gold_facts=["млин на південь від села порожній з минулої осені", "мірошник пішов, нікому нічого не сказавши", "Любисток бачив світло в млині минулої ночі"],
      gold_state=[]),
 dict(id="e03", present=["player", "guard", "merchant"], location="Корчма «Під сірою мишею»",
      segments=[("player", "Я мовчки оголюю срібний меч і кладу його на стіл."),
                ("narration", "Вартовий кладе руку на руків'я. Купець зблід і відсунув кошик із сиром.")],
      state=[], gold_facts=["Рагнар оголив срібний меч і поклав його на стіл", "вартовий поклав руку на руків'я меча"],
      gold_state=[("player", "equipment", "reveal", "срібний меч")]),
 dict(id="e04", present=["player", "triss"], location="Кімната Тріс",
      segments=[("narration", "Тріс обробляє рану Рагнара настоєм і накладає пов'язку з чистого полотна. Вона каже, що рана затягнеться за тиждень, але до того не можна піднімати меч правою рукою.")],
      state=[("player", "injury", "глибока рана на передпліччі", True)],
      gold_facts=["Тріс обробила рану Рагнара настоєм", "рана затягнеться за тиждень", "Рагнарові не можна піднімати меч правою рукою тиждень"],
      gold_state=[("player", "injury", "add", "пов'язка на передпліччі")]),
 dict(id="e05", present=["player", "smith", "child"], location="Ринок",
      segments=[("narration", "Коваль каже, що підкувати коня коштує п'ять крон. Дівчинка тягне Рагнара за рукав і питає, чи справді він убиває чудовиськ. Рагнар мовчить.")],
      state=[], gold_facts=["підкувати коня коштує п'ять крон", "дівчинка спитала Рагнара, чи він убиває чудовиськ"], gold_state=[]),
 dict(id="e06", present=["player", "lambert"], location="Зала Каер Морхену",
      segments=[("narration", "Ламберт сплюнув і викинув у вогонь розірваний плащ Рагнара. Новий плащ, сірий, він кинув Рагнарові з роздратованим «візьми»."),
                ("lambert", "Візьми цей і не загуби.")],
      state=[("player", "clothing", "розірваний плащ", True)],
      gold_facts=["Ламберт спалив розірваний плащ Рагнара", "Ламберт дав Рагнарові новий сірий плащ"],
      gold_state=[("player", "clothing", "remove", "розірваний плащ"), ("player", "clothing", "add", "сірий плащ")]),
 dict(id="e07", present=["player", "roche"], location="Лісова дорога",
      segments=[("roche", "Купці кажуть, що за Яругою стоять нільфгаардські полки. Не вір чуткам, але й не ігноруй."),
                ("narration", "Роше стискає в кулаці маленький срібний значок «Блакитних смуг» і ховає його під плащ.")],
      state=[], gold_facts=["Роше чув від купців, що за Яругою стоять нільфгаардські полки (чутка)", "Роше сховав значок «Блакитних смуг» під плащ"],
      gold_state=[("roche", "equipment", "hide", "срібний значок «Блакитних смуг»")]),
 dict(id="e08", present=["player", "coen"], location="Нічний табір",
      segments=[("narration", "Койон помітив, що Рагнар блідий і спітнілий, але промовчав. Він підкидає хмиз у вогнище й залишається на варті до світанку.")],
      state=[], gold_facts=["Койон помітив, що Рагнар блідий і спітнілий", "Койон залишився на варті до світанку"],
      gold_state=[("player", "injury", "add", "блідість і піт")]),
 dict(id="e09", present=["player", "jaskier", "hostomyl"], location="Придорожня корчма",
      segments=[("jaskier", "Кажуть, що в селі за лісом оселився чоловік у масці. Не питайте, звідки я знаю: мені розповіла його коханка, кухарка."),
                ("narration", "Корчмар Гостомил у цей час мовчки рахував гроші й не слухав.")],
      state=[], gold_facts=["Любисток каже, що в селі за лісом оселився чоловік у масці", "джерело Любистка — кухарка, коханка цього чоловіка"],
      gold_state=[]),
 dict(id="e10", present=["player", "eskel", "vesemir"], location="Подвір'я Каер Морхену",
      segments=[("narration", "Ескель ударив Рагнара тренувальним мечем по ребрах; Рагнар упав на коліно й видихнув. Весемір з порога крикнув, що на сьогодні досить, і пішов по воду.")],
      state=[], gold_facts=["Ескель ударив Рагнара тренувальним мечем по ребрах", "Весемір сказав, що на сьогодні тренування досить"],
      gold_state=[("player", "injury", "add", "забиті ребра")]),
]


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "narrator.json").write_text(json.dumps(NARR, ensure_ascii=False, indent=1))
    (OUT / "npc.json").write_text(json.dumps(NPC, ensure_ascii=False, indent=1))
    (OUT / "extract.json").write_text(json.dumps(EXT, ensure_ascii=False, indent=1))
    (OUT / "profiles.json").write_text(json.dumps(dict(names=NAMES, profiles=PROFILES), ensure_ascii=False, indent=1))
    print(len(NARR), len(NPC), len(EXT))


if __name__ == "__main__":
    main()
