"""
Acoustic Echo Cancellation (AEC) module using pyaec.
Removes Gemini's output voice from system loopback audio using precompiled Rust-backed AEC.
Fully portable for third-party audio projects.
"""

import sys
import numpy as np
from typing import Optional

try:
    from pyaec import EchoCanceller
    HAS_PYAEC = True
except ImportError:
    HAS_PYAEC = False


class EchoCancellationFilter:
    """Applies Acoustic Echo Cancellation (AEC) using pyaec to eliminate speaker feedback."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1, tail_length_ms: int = 200):
        self._sample_rate = sample_rate
        self._channels = channels
        self._canceller = None
        self._last_far_end = b""
        if HAS_PYAEC:
            try:
                self._canceller = EchoCanceller(tail_length_ms=tail_length_ms, sample_rate=sample_rate)
            except Exception as e:
                print(f"Warning: Failed to initialize pyaec EchoCanceller: {e}", file=sys.stderr)
                self._canceller = None

    def analyze_reference(self, reference_chunk: np.ndarray) -> None:
        """Cache Gemini's output audio playback chunk as far-end reference."""
        if reference_chunk is not None and len(reference_chunk) > 0:
            self._last_far_end = reference_chunk.tobytes()

    def process_stream(self, loopback_chunk: np.ndarray) -> np.ndarray:
        """Process incoming loopback audio chunk (near-end) against far-end reference using pyaec."""
        if not self._canceller or loopback_chunk is None or len(loopback_chunk) == 0:
            return loopback_chunk

        near_bytes = loopback_chunk.tobytes()
        far_bytes = self._last_far_end
        if not far_bytes:
            # If no speech is playing, supply silent far-end buffer of matching length
            far_bytes = b"\x00" * len(near_bytes)

        try:
            cleaned_bytes = self._canceller.process(near_end=near_bytes, far_end=far_bytes)
            return np.frombuffer(cleaned_bytes, dtype=np.int16)
        except Exception:
            return loopback_chunk
