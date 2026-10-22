# Portraits

One YAML file per NPC in this folder. The engine never sends a whole portrait to the model:
code picks one stance for the current rung and situation and sends a slice of at most 260 words.
Write your own paraphrase, no book excerpts. Do not add facts the NPC has not learned.

Required fields: `id`, `character` (profile id), `name`, `phase`, `core`, `stances`, `hidden`,
`leaks` (list), `voice`, `never`. Optional: `switches`, `relations`.

- `rung` values: stranger, client, ally, close, lover, rival, enemy, subordinate. Fallback for a
  missing rung goes to the nearest on `stranger < client < ally < close < lover`; rival, enemy and
  subordinate fall back to stranger.
- A stance has `id`, `rung` (list), `does`, `sounds`; optional `when` (keys `power` self|other|even,
  `audience` true|false, `stakes` low|high|mortal), `tail`, `examples`. A stance with `when` wins
  over one without when both match the rung. At most 2 examples are used.
- A switch has `id`, `trigger` (an English yes/no question about what the player just did),
  `warmth` and `trust` (numbers), optional `note`.
- `relations` maps another character id to a rung (static NPC to NPC).

```yaml
id: mira_early
character: mira
name: Mira
phase: early
core: A careful ferrywoman who counts every coin and trusts slowly.
stances:
  - id: guarded
    rung: [stranger, client]
    does: Answers what is asked and nothing more; keeps the oar between herself and the customer.
    sounds: Short, dry, practical.
    examples: ["Two coins. Cash first."]
  - id: guarded_crowd
    rung: [stranger]
    when: {audience: true}
    does: Stays brisk and avoids anything personal.
    sounds: Loud and businesslike.
switches:
  - id: paid_debt
    trigger: Did the player offer to settle her debt?
    warmth: 0.3
    trust: 0.2
hidden: She owes money to the harbour master.
leaks:
  - Her eyes drift to the purse at your belt.
voice: Short sentences, river slang.
never: Never begs and never asks for help outright.
relations:
  harbour_master: enemy
```
