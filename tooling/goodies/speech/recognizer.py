"""
Local Vosk model wrapper for turning microphone audio into finalized phrases.
"""

import os
import sys
import json
import queue
from typing import Optional

import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer

from .config import VOSK_MODEL_PATH, MIC_SAMPLE_RATE


class SpeechRecognizer:
    """Wraps a local Vosk model to turn microphone audio into finalized phrases."""

    def __init__(self, model_path: str = VOSK_MODEL_PATH, samplerate: int = MIC_SAMPLE_RATE):
        if not os.path.exists(model_path):
            print(f"Please place your local offline Vosk '{model_path}' folder in this directory.")
            sys.exit(1)
        self._recognizer = KaldiRecognizer(Model(model_path), samplerate)
        self._audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self._level = 0.0  # crude, cosmetic loudness reading for the terminal meter
        self._stream = sd.RawInputStream(
            samplerate=samplerate,
            blocksize=4000,
            dtype="int16",
            channels=1,
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)
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
