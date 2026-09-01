"""
Local Vosk model wrapper for turning microphone audio into finalized phrases.
"""

import os
import json
import queue
from typing import TYPE_CHECKING, Optional

import numpy as np

from infrastructure.logger import log

# `load_user_config` lives in storage/configs/config_manager.py which is
# created in a later phase of the speech work. Make the import tolerant
# so this module remains importable in the meantime (e.g. for unit
# tests) — when the config module isn't available, the helpers below
# fall back to built-in defaults.
try:
    from cabinet.configs.config_manager import load_user_config
except ImportError:
    load_user_config = None  # type: ignore[assignment]

if TYPE_CHECKING:
    import sounddevice as _sd
    from vosk import Model, KaldiRecognizer

MODULE_NAME = "SpeechRecognizer"

# Fallback defaults matching the original gemini_speech config. These are
# used if the user's config does not override them.
_DEFAULT_VOSK_MODEL_PATH = "model"
_DEFAULT_MIC_SAMPLE_RATE = 16000


def _resolve_config_defaults() -> tuple[str, int]:
    """Pull Vosk model path / mic sample rate from user config with safe fallbacks."""
    if load_user_config is None:
        return _DEFAULT_VOSK_MODEL_PATH, _DEFAULT_MIC_SAMPLE_RATE
    try:
        cfg = load_user_config() or {}
        speech = cfg.get("speech") or {}
        model_path = speech.get("vosk_model_path") or _DEFAULT_VOSK_MODEL_PATH
        sample_rate = int(speech.get("mic_sample_rate") or _DEFAULT_MIC_SAMPLE_RATE)
    except Exception as exc:
        log("Could not load speech config, using built-in defaults: {}", exc, level="warning")
        model_path = _DEFAULT_VOSK_MODEL_PATH
        sample_rate = _DEFAULT_MIC_SAMPLE_RATE
    return model_path, sample_rate


class SpeechRecognizer:
    """Wraps a local Vosk model to turn microphone audio into finalized phrases."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        samplerate: Optional[int] = None,
    ):
        if model_path is None or samplerate is None:
            cfg_path, cfg_rate = _resolve_config_defaults()
            if model_path is None:
                model_path = cfg_path
            if samplerate is None:
                samplerate = cfg_rate

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Local offline Vosk model folder not found at '{model_path}'. "
                "Please download and place model files there."
            )
        # Lazy-import heavy native deps so this module is importable in
        # environments where the Vosk/sounddevice libs are not installed
        # (e.g. unit tests that mock out the recognizer entirely).
        import sounddevice as _sd
        from vosk import Model, KaldiRecognizer
        self._recognizer = KaldiRecognizer(Model(model_path), samplerate)
        self._audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self._level = 0.0  # crude, cosmetic loudness reading for the terminal meter
        self._stream = _sd.RawInputStream(
            samplerate=samplerate,
            blocksize=4000,
            dtype="int16",
            channels=1,
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        if status:
            log("Audio input status: {}", status, level="warning")
        samples = np.frombuffer(indata, dtype=np.int16)
        if len(samples):
            # Not calibrated to anything acoustic — just scaled to look
            # reasonable for typical mic gain and speaking volume.
            self._level = min(1.0, float(np.abs(samples).mean()) / 2000.0)
        self._audio_queue.put(bytes(indata))

    def __enter__(self) -> "SpeechRecognizer":
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stream.stop()
        self._stream.close()

    def reset(self) -> None:
        """Clear buffered audio and recognizer state.

        Call this right after sending a phrase, so the AI's own voice
        played back through the speakers doesn't get picked back up and
        transcribed as if the player said it.
        """
        self._recognizer.Reset()
        with self._audio_queue.mutex:
            self._audio_queue.queue.clear()

    def poll(self) -> Optional[str]:
        """Drain buffered mic audio and return a finalized phrase, if ready."""
        phrase = None
        while not self._audio_queue.empty():
            data = self._audio_queue.get_nowait()
            if self._recognizer.AcceptWaveform(data):
                result = json.loads(self._recognizer.Result())
                text = result.get("text", "").strip()
                if text:
                    phrase = text
        return phrase

    def level(self) -> float:
        """Current mic loudness, roughly 0.0–1.0, for the terminal meter."""
        return self._level
