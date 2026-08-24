"""Narrative memory summarization prompt templates."""

NARRATIVE_MEDIUM_TERM_PROMPT = (
    "Summarize the following recent gameplay turns into a concise 2-3 sentence "
    "situational summary capturing key events, stakes, and narrative direction:\n\n"
    "{buffer_text}"
)

NARRATIVE_LONG_TERM_PROMPT = (
    "Synthesize the following situational summaries into a single cohesive strategic "
    "long-term overview for the entire run so far:\n\n"
    "{med_text}"
)
