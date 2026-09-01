"""
Buffers Vosk's per-pause finalized fragments into one cohesive utterance.
"""

import time
from typing import Optional

from infrastructure.logger import log

# `load_user_config` lives in storage/configs/config_manager.py which is
# created in a later phase of the speech work. Make the import tolerant.
try:
    from cabinet.configs.config_manager import load_user_config
except ImportError:
    load_user_config = None  # type: ignore[assignment]

MODULE_NAME = "UtteranceAssembler"

# Fallback default matching the original gemini_speech config.
_DEFAULT_THINKING_PAUSE_SECONDS = 0.7


def _resolve_thinking_pause() -> float:
    """Pull thinking-pause seconds from user config with safe fallback."""
    if load_user_config is None:
        return _DEFAULT_THINKING_PAUSE_SECONDS
    try:
        cfg = load_user_config() or {}
        speech = cfg.get("speech") or {}
        return float(speech.get("thinking_pause_seconds") or _DEFAULT_THINKING_PAUSE_SECONDS)
    except Exception:
        return _DEFAULT_THINKING_PAUSE_SECONDS


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

    def __init__(self, pause_seconds: Optional[float] = None):
        if pause_seconds is None:
            pause_seconds = _resolve_thinking_pause()
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
