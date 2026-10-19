"""Engine settings that live in one place.

Languages (task 9): what the player reads is Ukrainian by default. Records and judgment questions
stay as they are until the language experiment (task 10) decides; `DEFAULT_RECORD_LANGUAGE = None`
means "no instruction", i.e. whatever the extractor model writes now. Switch records to English
by setting it to "English" (here, or `Engine(record_language=...)`).
"""
DEFAULT_OUTPUT_LANGUAGE: str | None = "Ukrainian"  # narration and NPC speech
DEFAULT_RECORD_LANGUAGE: str | None = None  # extractor facts and state items
NPC_REJECT_P = 0.7  # an NPC line is rejected when the check's suspicion reaches this
