"""Closed vocabularies for canon ingestion. Jev can choose from a list but cannot write."""
from __future__ import annotations

CHANNELS = ("witnessed", "heard", "overheard", "told", "hearsay", "read", "inferred", "sensed", "innate")

EKINDS = ("violence", "magic", "death", "crime", "politics", "law", "bargain", "conversation",
          "travel", "arrival", "revelation", "scandal", "monster", "ritual", "rumour", "intimate",
          "recovery", "other")

ATTITUDES = ("positive", "negative", "neutral", "ambivalent")

# reaction -> (party kinds it fits, description)
REACTIONS: dict[str, tuple[str, str]] = {
    "ignore": ("any", "takes no notice or does nothing"),
    "dismiss": ("any", "waves it off, ridicules, does not believe it matters"),
    "investigate": ("any", "asks questions, looks into it, gathers information"),
    "avoid": ("any", "keeps away from the matter or the person"),
    "flee": ("any", "runs away, leaves in fear"),
    "freeze": ("any", "is paralysed by fear or shock"),
    "appeal_to_authority": ("any", "turns to a ruler, official or guard for action"),
    "seek_protection": ("any", "looks for shelter, a guard, a charm"),
    "retaliate": ("any", "answers with violence or a threat of it"),
    "punish": ("ruler|official", "arrests, sentences or otherwise punishes"),
    "negotiate": ("any", "bargains, haggles, proposes terms"),
    "bribe_or_pay": ("any", "offers money or favour to change the outcome"),
    "conceal": ("any", "hides, lies or keeps it quiet"),
    "exploit": ("any", "uses it for own gain or advantage"),
    "mobilise": ("ruler|faction", "gathers people, force or resources"),
    "comply": ("any", "obeys, submits, does as told"),
    "defend": ("any", "protects someone or something"),
    "support": ("any", "helps, backs, or agrees with one side"),
    "mourn": ("any", "grieves"),
    "accept": ("any", "comes to terms, resigns oneself"),
    "scheme": ("any", "plots or prepares something covertly"),
    "hire_help": ("ruler|official|faction", "sends for or hires an expert"),
    "warn": ("any", "warns or advises someone"),
    "gossip": ("crowd|faction", "spreads the story, talks it over"),
    "demand": ("any", "insists, threatens, sets conditions"),
    "challenge": ("any", "confronts, insults or provokes"),
    "admire": ("any", "respects, trusts, is impressed"),
}

# in-world part of day -> hour
PARTS = {"dawn": 5, "morning": 9, "noon": 12, "afternoon": 15, "evening": 19, "night": 23}
