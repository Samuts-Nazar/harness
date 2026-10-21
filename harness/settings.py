"""Engine settings that live in one place.

Languages (task 9, 10): what the player reads is Ukrainian by default. Records are English with
Ukrainian names (task 10; names via the glossary, task 12). `record_language=None` means "no
instruction": whatever the extractor model writes.
"""
DEFAULT_OUTPUT_LANGUAGE: str | None = "Ukrainian"  # narration and NPC speech
DEFAULT_RECORD_LANGUAGE: str | None = "English"  # extractor facts and state items (task 10); names stay Ukrainian
DEFAULT_NARRATION = "prose"  # "prose": free text, speakers/actions from the scene director; "json": task 3 contract
MAX_SPEAKERS = 2  # the scene director names at most this many speakers per turn
NPC_REJECT_P = 0.7  # an NPC line is rejected when the check's suspicion reaches this
DEFAULT_DIALOGUE = "living"  # "living": the director picks each next line (task LD-4); "classic": MAX_SPEAKERS
MAX_EXCHANGE_LINES = 6  # living mode: at most this many director steps (NPC lines) per player turn
