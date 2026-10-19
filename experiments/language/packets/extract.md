# extract packet (blind)


## e01
Passage: [['player', 'Я кладу на стіл голову кікімори й питаю Весеміра про нагороду.'], ['narration', 'Рагнар кидає на стіл голову кікімори. Весемір оглядає її й киває: селяни з долини обіцяли двісті оренів. Свіжий порізок на щоці Рагнара ще кровить.']]
State: []
GOLD facts: ['Рагнар приніс голову кікімори', 'селяни з долини обіцяли двісті оренів за кікімору']
GOLD state: [['player', 'injury', 'add', 'порізок на щоці']]


### A
FACTS:
  - Ragnar places a kikimora's head on the table and asks Vesemir about the reward.
  - Vesemir examines the kikimora's head and nods.
  - The villagers from the valley promised two hundred orens as a reward.
  - A fresh cut on Ragnar's cheek is still bleeding.
CHANGES:
  - player/injury/add: fresh bleeding cut on cheek


### B
FACTS:
  - Ragnar places a kikimora's head on the table and asks Vesemir about the reward.
  - Vesemir examines the kikimora's head and nods.
  - The villagers from the valley promised two hundred orens as a reward.
  - A fresh cut on Ragnar's cheek is still bleeding.
CHANGES:
  - player/injury/add: fresh bleeding cut on cheek


### C
FACTS:
  - Весемір оглянув голову кікімори, яку Рагнар поклав на стіл.
  - Селяни з долини обіцяли нагороду у двісті оренів.
  - У Рагнара на щоці свіжий поріз, який ще кровить.
CHANGES:
  - player/injury/add: свіжий поріз на щоці, що кровить


### D
FACTS:
  - Рагнар поклав на стіл голову кікімори.
  - Весемір оглянув голову кікімори й кивнув.
  - Селяни з долини обіцяли нагороду у двісті оренів за голову кікімори.
  - У Рагнара на щоці свіжий порізок, який ще кровить.
CHANGES:
  - player/injury/add: свіжий порізок на щоці, який ще кровить


### E
FACTS:
  - Ragnar places a kikimora's head on the table and asks Vesemir about the reward.
  - Vesemir examines the kikimora's head and nods, confirming the valley villagers promised two hundred orens.
  - A fresh cut on Ragnar's cheek is still bleeding.
CHANGES:
  - player/injury/add: bleeding cut on cheek


### F
FACTS:
  - Рагнар поклав на стіл голову кікімори.
  - Весемір оглянув голову кікімори й кивнув.
  - Селяни з долини обіцяли нагороду у двісті оренів.
  - У Рагнара на щоці свіжий порізок, який ще кровить.
CHANGES:
  - player/injury/add: свіжий порізок на щоці, який ще кровить


## e02
Passage: [['narration', 'Корчмар Гостомил розповідає, що млин на південь від села стоїть порожній із минулої осені, і що мірошник пішов, не сказавши ні слова. Любисток вставляє, що бачив там світло минулої ночі.']]
State: []
GOLD facts: ['млин на південь від села порожній з минулої осені', 'мірошник пішов, нікому нічого не сказавши', 'Любисток бачив світло в млині минулої ночі']
GOLD state: []


### A
FACTS:
  - Млин на південь від села стоїть порожній із минулої осені.
  - Мірошник пішов, не сказавши ні слова.
  - Любисток бачив світло на млині минулої ночі.
CHANGES:



### B
FACTS:
  - The mill south of the village has stood empty since last autumn.
  - The miller left without saying a word.
  - Jaskier saw a light at the mill last night.
CHANGES:



### C
FACTS:
  - Млин на південь від села стоїть порожній із минулої осені.
  - Мірошник пішов, не сказавши ні слова.
  - Любисток бачив світло в млині минулої ночі.
CHANGES:



### D
FACTS:
  - Млин на південь від села стоїть порожній із минулої осені.
  - Мірошник пішов, не сказавши ні слова.
  - Любисток бачив світло в млині минулої ночі.
CHANGES:



### E
FACTS:
  - The mill south of the village has stood empty since last autumn.
  - The miller left without saying a word.
  - Jaskier saw a light at the mill last night.
CHANGES:



### F
FACTS:
  - The mill south of the village has stood empty since last autumn.
  - The miller left without saying a word.
  - Jaskier saw a light at the mill last night.
CHANGES:



## e03
Passage: [['player', 'Я мовчки оголюю срібний меч і кладу його на стіл.'], ['narration', "Вартовий кладе руку на руків'я. Купець зблід і відсунув кошик із сиром."]]
State: []
GOLD facts: ['Рагнар оголив срібний меч і поклав його на стіл', "вартовий поклав руку на руків'я меча"]
GOLD state: [['player', 'equipment', 'reveal', 'срібний меч']]


### A
FACTS:
  - Гравець оголив срібний меч і поклав його на стіл.
  - Вартовий поклав руку на руків'я.
  - Купець зблід і відсунув кошик із сиром.
CHANGES:
  - player/equipment/reveal: срібний меч
  - merchant/inventory/remove: кошик із сиром


### B
FACTS:
  - Гравець кладе оголений срібний меч на стіл.
  - Вартовий кладе руку на руків'я.
  - Купець зблід і відсунув кошик із сиром.
CHANGES:
  - player/equipment/reveal: срібний меч
  - merchant/inventory/reveal: кошик із сиром


### C
FACTS:
  - The player silently draws a silver sword and places it on the table.
  - The guard puts a hand on the hilt of a weapon.
  - The merchant pales and pushes away a basket of cheese.
CHANGES:
  - player/equipment/reveal: silver sword


### D
FACTS:
  - The player silently draws a silver sword and places it on the table.
  - The guard puts a hand on the hilt of his weapon.
  - The merchant turns pale and pushes away a basket of cheese.
CHANGES:
  - player/equipment/reveal: silver sword


### E
FACTS:
  - Гравець має срібний меч.
  - Гравець поклав срібний меч на стіл.
  - Вартовий поклав руку на руків'я.
  - Купець зблід.
  - Купець відсунув кошик із сиром.
CHANGES:
  - player/equipment/add: срібний меч


### F
FACTS:
  - The player silently draws a silver sword and places it on the table.
  - The guard puts a hand on the hilt of his weapon.
  - The merchant turns pale and pushes away a basket of cheese.
CHANGES:
  - player/equipment/reveal: silver sword
  - merchant/inventory/remove: basket of cheese


## e04
Passage: [['narration', "Тріс обробляє рану Рагнара настоєм і накладає пов'язку з чистого полотна. Вона каже, що рана затягнеться за тиждень, але до того не можна піднімати меч правою рукою."]]
State: [['player', 'injury', 'глибока рана на передпліччі', True]]
GOLD facts: ['Тріс обробила рану Рагнара настоєм', 'рана затягнеться за тиждень', 'Рагнарові не можна піднімати меч правою рукою тиждень']
GOLD state: [['player', 'injury', 'add', "пов'язка на передпліччі"]]


### A
FACTS:
  - Тріс обробила рану Рагнара настоєм і наклала пов'язку з чистого полотна.
  - Рана Рагнара затягнеться за тиждень, але до того не можна піднімати меч правою рукою.
CHANGES:
  - player/injury/add: пов'язка з чистого полотна на рані


### B
FACTS:
  - Triss treats Ragnar's wound with a tincture and applies a bandage made of clean linen.
  - Triss says the wound will heal within a week, but until then the sword must not be lifted with the right arm.
CHANGES:
  - player/injury/add: пов'язка з чистого полотна на передпліччі


### C
FACTS:
  - Тріс обробила рану Рагнара настоєм і наклала пов'язку з чистого полотна.
  - Рана Рагнара затягнеться за тиждень, але до того не можна піднімати меч правою рукою.
CHANGES:
  - player/injury/add: пов'язка з чистого полотна на передпліччі


### D
FACTS:
  - Тріс обробила рану Рагнара настоєм і наклала пов'язку з чистого полотна.
  - Рана Рагнара затягнеться за тиждень, але до того не можна піднімати меч правою рукою.
CHANGES:
  - player/injury/add: пов'язка з чистого полотна на рані передпліччя


### E
FACTS:
  - Triss treats Ragnar's wound with a tincture and wraps it with clean linen bandages.
  - Triss says the wound will heal within a week.
  - Triss says Ragnar must not lift a sword with his right hand until the wound heals.
CHANGES:
  - player/injury/add: пов'язка з чистого полотна на рані


### F
FACTS:
  - Triss treats Ragnar's wound with a tincture and applies a bandage made of clean linen.
  - Triss says the wound will heal within a week, but until then he must not lift a sword with his right hand.
CHANGES:
  - player/injury/add: bandage of clean linen on forearm wound


## e05
Passage: [['narration', "Коваль каже, що підкувати коня коштує п'ять крон. Дівчинка тягне Рагнара за рукав і питає, чи справді він убиває чудовиськ. Рагнар мовчить."]]
State: []
GOLD facts: ["підкувати коня коштує п'ять крон", 'дівчинка спитала Рагнара, чи він убиває чудовиськ']
GOLD state: []


### A
FACTS:
  - Підкувати коня коштує п'ять крон.
  - Дівчинка питає Рагнара, чи справді він убиває чудовиськ.
  - Рагнар мовчить у відповідь на питання дівчинки.
CHANGES:



### B
FACTS:
  - Підкувати коня коштує п'ять крон.
  - Дівчинка питає Рагнара, чи справді він убиває чудовиськ.
CHANGES:



### C
FACTS:
  - Підкувати коня коштує п'ять крон.
  - Дівчинка тягне Рагнара за рукав і питає, чи справді він убиває чудовиськ.
  - Рагнар мовчить у відповідь на питання дівчинки.
CHANGES:



### D
FACTS:
  - The smith says that shoeing a horse costs five crowns.
  - The girl pulls Ragnar's sleeve and asks whether he really kills monsters.
  - Ragnar stays silent.
CHANGES:



### E
FACTS:
  - The smith says that shoeing a horse costs five crowns.
  - The girl tugs at Ragnar's sleeve and asks whether he really kills monsters.
  - Ragnar stays silent.
CHANGES:



### F
FACTS:
  - The smith says shoeing a horse costs five crowns.
  - The girl tugs at Ragnar's sleeve and asks whether he really kills monsters.
  - Ragnar stays silent.
CHANGES:



## e06
Passage: [['narration', 'Ламберт сплюнув і викинув у вогонь розірваний плащ Рагнара. Новий плащ, сірий, він кинув Рагнарові з роздратованим «візьми».'], ['lambert', 'Візьми цей і не загуби.']]
State: [['player', 'clothing', 'розірваний плащ', True]]
GOLD facts: ['Ламберт спалив розірваний плащ Рагнара', 'Ламберт дав Рагнарові новий сірий плащ']
GOLD state: [['player', 'clothing', 'remove', 'розірваний плащ'], ['player', 'clothing', 'add', 'сірий плащ']]


### A
FACTS:
  - Lambert spat and threw Ragnar's torn cloak into the fire.
  - Lambert tossed Ragnar a new gray cloak with an irritated "take it."
  - Lambert told Ragnar to take the cloak and not lose it.
CHANGES:
  - player/clothing/remove: розірваний плащ
  - player/clothing/add: новий сірий плащ


### B
FACTS:
  - Ламберт викинув у вогонь розірваний плащ Рагнара.
  - Ламберт дав Рагнару новий сірий плащ.
CHANGES:
  - player/clothing/remove: розірваний плащ
  - player/clothing/add: новий сірий плащ


### C
FACTS:
  - Lambert spat and threw Ragnar's torn cloak into the fire.
  - Lambert threw Ragnar a new grey cloak with an irritated 'take it'.
  - Lambert told Ragnar to take the cloak and not lose it.
CHANGES:
  - player/clothing/remove: розірваний плащ
  - player/clothing/add: новий сірий плащ


### D
FACTS:
  - Ламберт викинув у вогонь розірваний плащ Рагнара.
  - Ламберт дав Рагнару новий сірий плащ.
CHANGES:
  - player/clothing/remove: розірваний плащ
  - player/clothing/add: новий сірий плащ


### E
FACTS:
  - Lambert threw Ragnar's torn cloak into the fire.
  - Lambert gave Ragnar a new grey cloak.
  - Lambert told Ragnar to take the cloak and not lose it.
CHANGES:
  - player/clothing/remove: розірваний плащ
  - player/clothing/add: новий сірий плащ


### F
FACTS:
  - Ламберт викинув у вогонь розірваний плащ Рагнара.
  - Ламберт дав Рагнару новий сірий плащ.
  - Ламберт з роздратуванням сказав Рагнару взяти новий плащ і не загубити його.
CHANGES:
  - player/clothing/remove: розірваний плащ
  - player/clothing/add: новий сірий плащ


## e07
Passage: [['roche', 'Купці кажуть, що за Яругою стоять нільфгаардські полки. Не вір чуткам, але й не ігноруй.'], ['narration', 'Роше стискає в кулаці маленький срібний значок «Блакитних смуг» і ховає його під плащ.']]
State: []
GOLD facts: ['Роше чув від купців, що за Яругою стоять нільфгаардські полки (чутка)', 'Роше сховав значок «Блакитних смуг» під плащ']
GOLD state: [['roche', 'equipment', 'hide', 'срібний значок «Блакитних смуг»']]


### A
FACTS:
  - Nilfgaardian regiments are said to be stationed beyond the Yaruga river.
CHANGES:
  - roche/inventory/hide: small silver 'Blue Stripes' badge


### B
FACTS:
  - Купці кажуть, що за Яругою стоять нільфгаардські полки.
CHANGES:
  - roche/inventory/add: маленький срібний значок «Блакитних смуг»


### C
FACTS:
  - За Яругою стоять нільфгаардські полки.
CHANGES:
  - roche/inventory/add: маленький срібний значок «Блакитних смуг»


### D
FACTS:
  - Nilfgaardian regiments are said to be stationed beyond the Yaruga river.
  - Roche keeps a small silver badge of the Blue Stripes.
CHANGES:
  - roche/inventory/add: small silver badge of the Blue Stripes


### E
FACTS:
  - Nilfgaardian regiments are said to be stationed beyond the Yaruga river.
  - Roche carries a small silver badge of the Blue Stripes.
CHANGES:
  - roche/inventory/add: small silver badge of the Blue Stripes


### F
FACTS:
  - Купці кажуть, що за Яругою стоять нільфгаардські полки.
CHANGES:
  - roche/inventory/hide: маленький срібний значок «Блакитних смуг»


## e08
Passage: [['narration', 'Койон помітив, що Рагнар блідий і спітнілий, але промовчав. Він підкидає хмиз у вогнище й залишається на варті до світанку.']]
State: []
GOLD facts: ['Койон помітив, що Рагнар блідий і спітнілий', 'Койон залишився на варті до світанку']
GOLD state: [['player', 'injury', 'add', 'блідість і піт']]


### A
FACTS:
  - Ragnar was pale and sweating.
  - Coen noticed Ragnar's condition but said nothing.
  - Coen added kindling to the campfire.
  - Coen stayed on watch until dawn.
CHANGES:



### B
FACTS:
  - Рагнар блідий і спітнілий.
  - Койон помітив, що Рагнар блідий і спітнілий, але промовчав.
  - Койон підкидає хмиз у вогнище.
  - Койон залишається на варті до світанку.
CHANGES:



### C
FACTS:
  - Ragnar is pale and sweating.
  - Coen noticed Ragnar's pale and sweaty condition but said nothing.
  - Coen adds brushwood to the campfire.
  - Coen stays on watch until dawn.
CHANGES:



### D
FACTS:
  - Рагнар блідий і спітнілий.
  - Койон помітив стан Рагнара, але промовчав.
  - Койон підкидає хмиз у вогнище.
  - Койон залишається на варті до світанку.
CHANGES:



### E
FACTS:
  - Рагнар блідий і спітнілий.
  - Койон помітив, що Рагнар блідий і спітнілий, але промовчав.
  - Койон підкидає хмиз у вогнище.
  - Койон залишається на варті до світанку.
CHANGES:



### F
FACTS:
  - Ragnar is pale and sweaty.
  - Coen noticed Ragnar's pale and sweaty condition but said nothing.
  - Coen adds kindling to the campfire.
  - Coen stays on watch until dawn.
CHANGES:



## e09
Passage: [['jaskier', 'Кажуть, що в селі за лісом оселився чоловік у масці. Не питайте, звідки я знаю: мені розповіла його коханка, кухарка.'], ['narration', 'Корчмар Гостомил у цей час мовчки рахував гроші й не слухав.']]
State: []
GOLD facts: ['Любисток каже, що в селі за лісом оселився чоловік у масці', 'джерело Любистка — кухарка, коханка цього чоловіка']
GOLD state: []


### A
FACTS:
  - A man in a mask has settled in the village beyond the forest.
  - Jaskier learned about the masked man from the man's lover, a cook.
  - The innkeeper Hostomyl was silently counting money and not listening.
CHANGES:



### B
FACTS:
  - У селі за лісом оселився чоловік у масці.
  - Коханка чоловіка в масці — кухарка, яка розповіла про нього.
CHANGES:



### C
FACTS:
  - A man in a mask has settled in the village beyond the forest.
  - Jaskier learned about the masked man from the man's lover, a cook.
  - The innkeeper Hostomyl was silently counting money and not listening.
CHANGES:



### D
FACTS:
  - У селі за лісом оселився чоловік у масці.
  - Коханкою чоловіка в масці є кухарка, яка розповіла про нього.
  - Корчмар Гостомил у цей час мовчки рахував гроші й не слухав.
CHANGES:



### E
FACTS:
  - У селі за лісом оселився чоловік у масці.
  - Коханка чоловіка в масці — кухарка, яка розповіла про нього.
  - Корчмар Гостомил мовчки рахував гроші й не слухав.
CHANGES:



### F
FACTS:
  - A man wearing a mask has settled in the village beyond the forest.
  - Jaskier learned about the masked man from the man's lover, a cook, and refuses to say how else he knows.
  - The innkeeper Hostomyl was silently counting money and not listening during this time.
CHANGES:



## e10
Passage: [['narration', 'Ескель ударив Рагнара тренувальним мечем по ребрах; Рагнар упав на коліно й видихнув. Весемір з порога крикнув, що на сьогодні досить, і пішов по воду.']]
State: []
GOLD facts: ['Ескель ударив Рагнара тренувальним мечем по ребрах', 'Весемір сказав, що на сьогодні тренування досить']
GOLD state: [['player', 'injury', 'add', 'забиті ребра']]


### A
FACTS:
  - Ескель ударив Рагнара тренувальним мечем по ребрах.
  - Рагнар упав на коліно й видихнув після удару Ескеля.
  - Весемір крикнув з порога, що на сьогодні досить.
  - Весемір пішов по воду.
CHANGES:
  - eskel/equipment/add: тренувальний меч


### B
FACTS:
  - Ескель ударив Рагнара тренувальним мечем по ребрах.
  - Рагнар упав на коліно й видихнув після удару Ескеля.
  - Весемір крикнув з порога, що на сьогодні тренування досить.
  - Весемір пішов по воду.
CHANGES:



### C
FACTS:
  - Eskel struck Ragnar in the ribs with a training sword.
  - Ragnar fell to one knee and exhaled.
  - Vesemir called from the threshold that it was enough for today.
  - Vesemir went to fetch water.
CHANGES:



### D
FACTS:
  - Eskel struck Ragnar in the ribs with a training sword.
  - Ragnar fell to one knee and exhaled.
  - Vesemir shouted from the doorway that it was enough for today.
  - Vesemir went to fetch water.
CHANGES:



### E
FACTS:
  - Ескель ударив Рагнара тренувальним мечем по ребрах.
  - Рагнар упав на коліно й видихнув.
  - Весемір крикнув з порога, що на сьогодні тренування досить.
  - Весемір пішов по воду.
CHANGES:
  - player/injury/add: удар по ребрах


### F
FACTS:
  - Eskel struck Ragnar in the ribs with a training sword.
  - Ragnar fell to one knee and exhaled heavily.
  - Vesemir called from the doorway that training was enough for today and went to fetch water.
CHANGES:

