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

CROSS_SESSION_SUMMARY_PROMPT = (
    "You are Ally. Review the previous cross-session summary and the just-completed run's long-term overview to synthesize an updated, high-level cross-session summary for this game.\n\n"
    "Previous cross-session summary:\n{prior_cross_session}\n\n"
    "Just-completed run summary:\n{just_finished_run}\n\n"
    "Synthesize these into a single cohesive, high-level cross-session summary focusing on what we generally know about this game, persistent meta-strategies, and how runs tend to go. Do not give a blow-by-blow of the just-finished run."
)
