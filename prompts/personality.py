"""Personality redistillation prompt templates."""

PERSONALITY_DIGEST_PROMPT = (
    "Based on the following master reflection journal of our companion Ally, "
    "synthesize a comprehensive personality digest (200-400 words) capturing tone, "
    "quirks, and player relationship dynamics:\n\n"
    "{journal_text}"
)

PERSONALITY_MICRO_PROMPT = (
    "Boil down the following personality digest into an ultra-concise micro prompt (< 50 tokens) "
    "suitable for direct injection into a prompt to maintain voice consistency:\n\n"
    "{digest}"
)
