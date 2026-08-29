"""Personality redistillation prompt templates."""

PERSONALITY_DIGEST_PROMPT = (
    "Based on the following master reflection journal of our companion Ally, "
    "synthesize a comprehensive personality digest (200-400 words) capturing tone, "
    "quirks, and player relationship dynamics. If the journal reveals a pattern in "
    "how this companion tends to resolve tension between conflicting internal "
    "impulses, capture that pattern briefly as part of the digest -- but only if "
    "the journal actually shows it; don't invent one that isn't there:\n\n"
    "{journal_text}"
)

PERSONALITY_MICRO_PROMPT = (
    "Boil down the following personality digest into an ultra-concise micro prompt (< 50 tokens) "
    "suitable for direct injection into a prompt to maintain voice consistency:\n\n"
    "{digest}"
)
