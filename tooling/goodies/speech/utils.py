"""
Utility functions for transcript filtering, polishing, and ASCII mic-level display.
"""

from .config import SINGLE_WORD_WHITELIST, FILLER_WORDS, WAVE_WIDTH


def is_meaningful_phrase(phrase: str) -> bool:
    """Filter out likely noise: single words are only accepted if whitelisted.

    Multi-word phrases are always accepted, since background noise rarely
    gets misrecognized as more than one word.
    """
    words = phrase.split()
    if len(words) > 1:
        return True
    return words[0].lower() in SINGLE_WORD_WHITELIST


# Vosk's output is lowercase with no punctuation ("is that death"). Guessing
# a question mark for these leading words covers most spoken questions
# cheaply; anything else defaults to a period.
_QUESTION_STARTERS = {
    "who", "what", "when", "where", "why", "how",
    "is", "are", "am", "was", "were",
    "do", "does", "did",
    "can", "could", "would", "will", "should", "shall",
}


def polish_phrase(phrase: str) -> str:
    """Capitalize and punctuate a raw Vosk transcript.

    Purely cosmetic string handling — strip filler words, capitalize the
    first letter and any standalone "i", then append "?" or "." based on
    the first word. No model call, so it adds no meaningful latency.
    """
    words = phrase.split()
    stripped = [w for w in words if w.lower() not in FILLER_WORDS]
    if stripped:
        words = stripped
    words = ["I" if w == "i" else w for w in words]
    cleaned = " ".join(words)
    cleaned = cleaned[0].upper() + cleaned[1:]
    if words[0].lower() in _QUESTION_STARTERS:
        cleaned += "?"
    else:
        cleaned += "."
    return cleaned


def render_wave(level: float, width: int = WAVE_WIDTH) -> str:
    """Render a simple ASCII amplitude meter for live mic-level display."""
    filled = int(min(1.0, max(0.0, level)) * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"
