"""
Buffers Vosk's per-pause finalized fragments into one cohesive utterance.
"""

import time
from typing import Optional

from .config import THINKING_PAUSE_SECONDS


class UtteranceAssembler:
    """Buffers Vosk's per-pause finalized fragments into one utterance.

    Vosk finalizes on its own internal silence detection, which cuts a
    player off mid-thought if they pause. This holds each finalized
    fragment and only considers the utterance complete once
    `pause_seconds` has passed with no new fragment — letting the player
    pause to think without being cut off, the same problem real voice
    assistants solve with a trained end-of-utterance model, just handled
    here as a plain timer.
    """

    def __init__(self, pause_seconds: float = THINKING_PAUSE_SECONDS):
        self._pause_seconds = pause_seconds
        self._fragments: list[str] = []
        self._last_fragment_time: Optional[float] = None

    def add_fragment(self, fragment: str) -> None:
        self._fragments.append(fragment)
        self._last_fragment_time = time.monotonic()

    def has_pending(self) -> bool:
        return bool(self._fragments)

    def ready(self) -> bool:
        """True once enough silence has passed since the last fragment."""
        if not self._fragments or self._last_fragment_time is None:
            return False
        return (time.monotonic() - self._last_fragment_time) >= self._pause_seconds

    def flush(self) -> str:
        phrase = " ".join(self._fragments)
        self._fragments.clear()
        self._last_fragment_time = None
        return phrase
