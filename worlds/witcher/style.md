# Style sheet: the Witcher books in the Ukrainian translation

Written from a reading of the Ukrainian translation (Legeza and others). No quotation longer than a phrase.
`harness/style.py` reads this file by section (`## heading`); keep headings stable.
Language of the sheet: English, because the engine's prompts are English. Output stays Ukrainian.

## Dialogue
- Speech is written with the dash. Short lines trade back and forth; the answer is rarely the answer to the question asked (a question answered with a question, a joke, a number, a complaint).
- Gesture and business can carry the speech tags, when a line has one at all (many lines have none): wiping beer foam off the mouth, picking at an ear with a pen, watching the other man's hands, a look at the door, a spit. Plain "said" is rare; the verb is often a small act or a manner (урвав, буркнув, пирхнув, стенув плечима).
- People break themselves off, repeat a word, stall with "Ну…", "Ага", "Отож", "Га?", trail off with "…", then say the thing they came to say last, sideways.
- Address is by title or a rough nickname: "пане відьмаче", "старосто", "приятелю", "добрі люди", "вельможний пане поете". The politeness is often a weapon.
- Haggling is a duel: one number repeated like a stone, the other drifting upward in small steps; contempt for the other side's merchandise ("who were these dead anyway"); a deduction (tax, fee, "the clerk's share") ambushes the payout. Both sides know the game and enjoy it a little.
- The real business is stated late or not at all. First the weather, the road, the neighbour's cow, a complaint about officials, a superstition recited as hard fact.
- Oaths and small curses fit the speaker ("головою клянуся", "хай тебе чума", "на всіх демонів"). Fear shows in behaviour: talking too much, changing the subject, a glance at the dark, a lowered voice, an offer made too fast.

## Voices by class
- Villagers: slow, repeating, a word or two of local speech per speech, never a pile of dialect particles; listing every misfortune they have ever heard of, a crowd that adds items one by one; deference with suspicion; they fear the monster less than they fear paying and being cheated.
- Elders, officials, clerks: pompous, digressive, bureaucratic, proud of small authority; they stall; the money is always "for the town treasury".
- Innkeepers and merchants: practical, wary, money first, then fear for the premises; credit ended, the stick under the counter; hands busy with a cloth or a mug.
- Soldiers, mercenaries, thugs: coarse, short, mocking, sudden threats delivered casually.
- Witchers and hired professionals: curt, dry, understatement, never explain themselves; irony instead of anger.
- Mages, nobles, poets: long polished periods, learned words, mock courtesy, cruelty with a smile.
- Women with a stake in the matter (widows, innkeepers' wives): sharp, practical, say the unsayable, turn a question back on the asker, hide what they know behind a household detail.

## Irony and subtext
- Irony is dry and sits in the contrast: something lethal said in an everyday tone, something petty said with ceremony. The narrating voice and the characters both do it.
- Characters lie, bluff, fish, test; they rarely announce what they want. Subtext is carried by what is dodged.
- A digression that seems idle (a dead wife's proverb, a rumour about a neighbour) reveals the speaker.
- Humour never explains itself and never winks at the reader.

## Narration
- Ironic, worldly narrator who knows a little more than the hero and says it flatly. Short flat sentences for violence and danger, longer ones for crowds and talk.
- Concrete, ugly, specific detail: smell of wet wool and onions, a coin's weight, dirt under a nail, a dog scratching. Comparisons are rare and ordinary (see Plain words).
- The hero's alertness is shown through what he watches (hands, exits, a man's boots), not named as a feeling.
- Commentary in passing, an aside, sometimes a deflating one. Time and place anchored by one telling object, not by a paragraph of atmosphere.
- Scenes move: someone does something, someone reacts; the scene does not stop to summarise.

## Plain words
- Say the thing itself, in words a person would say aloud. No invented similes, sayings or aphorisms, in narration or in speech. Don't: «швидкий, професійний, як у коняка, що дивиться на коня», «люди — це не відповідь, це погода». Do: «Швидко глянув на меч, потім на руки». «Хто сказав? Ім'я».
- A comparison, if any, is one short ordinary thing («блідий, як крейда»), never a clause with «що…».
- Name an object by what it is, not by its material. Don't: «ходить у шовках», «тримає мідь». Do: «ходить у добрім вбранні», «тримає кухоль».
- No vague mystical non-events: nothing moves or happens by itself, nobody "better not wonder who". Don't: «склянка випрямилася сама — краще не розмірковувати, хто». Do: «Вона підсунула склянку рівніше».
- Speech is never fancier than the narration around it. A character answers in short literal sentences about the thing in front of them (price, road, a man's boots), the way a tavern talks.

## What it avoids
- Characters who state their motives, the stakes or a tidy summary of the situation; a neat closing offer that wraps the matter up.
- Direct, polite, business-meeting openings ("I have a matter", "we want you to", "what is your fee"). Nobody is that organised.
- Stock atmosphere (ominous, palpable silence, a chill down the spine, the air grew heavy), triple lists, symmetrical sentences, moralising.
- Filler adverbs of agreement and assurance ("звісно", "безумовно", "неодмінно") used as padding.
- Modern idiom, office or therapy language, anglicisms; everyone speaking in one register.
- Exclamation inflation. Strong feeling is shown by what a person does with their hands.
