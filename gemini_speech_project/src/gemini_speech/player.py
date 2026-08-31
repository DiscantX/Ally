"""
Gapless audio playback via a persistent sounddevice OutputStream.
"""

from typing import Optional, Callable
import sys
import threading
import queue
from collections import deque
import numpy as np

from .config import TTS_SAMPLE_RATE


class AudioPlayer:
    """Gapless audio playback via one long-lived, callback-driven output stream.

    Incoming PCM chunks are kept in a deque and only sliced out of the front
    chunk on each callback tick — never copied into one big buffer — so the
    lock the real-time callback needs is only ever held briefly. (An earlier
    version rebuilt the whole buffer with np.concatenate() on every incoming
    chunk; that copy could occasionally still be running when the callback
    needed the lock, causing rare, brief dropouts.) Because the device
    stream is opened exactly once for the whole session, there is also no
    per-chunk startup/teardown overhead, so consecutive chunks play
    back-to-back with no gaps between them.

    Each fresh utterance also waits for `prebuffer_ms` worth of audio to
    accumulate before playback starts, to absorb the initial delay while
    the network catches up. `latency="high"` asks PortAudio for a larger
    device-level buffer, giving brief Python-side scheduling delays more
    headroom to hide in before they become an audible gap.
    """

    def __init__(
        self,
        samplerate: int = TTS_SAMPLE_RATE,
        prebuffer_ms: int = 150,
        latency: str = "high",
        reference_callback: Optional[Callable] = None,
    ):
        self._samplerate = samplerate
        self._chunks: "deque[np.ndarray]" = deque()
        self._chunk_offset = 0
        self._buffered_samples = 0
        self._lock = threading.Lock()
        self._playing = threading.Event()
        self._priming = True
        self._prebuffer_samples = int(samplerate * prebuffer_ms / 1000)
        self._reference_callback = reference_callback
        self._reference_queue: "queue.Queue[np.ndarray]" = queue.Queue()
        self._stream = np.ndarray([])  # placeholder type hint for safety
        import sounddevice as sd
        self._stream = sd.OutputStream(
            samplerate=samplerate,
            channels=1,
            dtype="int16",
            blocksize=1024,
            latency=latency,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, outdata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)
        with self._lock:
            if self._priming:
                if self._buffered_samples < self._prebuffer_samples:
                    outdata[:, 0] = 0
                    return
                self._priming = False

            written = 0
            while written < frames and self._chunks:
                chunk = self._chunks[0]
                available_in_chunk = len(chunk) - self._chunk_offset
                take = min(available_in_chunk, frames - written)
                outdata[written:written + take, 0] = chunk[self._chunk_offset:self._chunk_offset + take]
                self._chunk_offset += take
                written += take
                self._buffered_samples -= take
                if self._chunk_offset >= len(chunk):
                    self._chunks.popleft()
                    self._chunk_offset = 0

            if written < frames:
                outdata[written:, 0] = 0

            if self._buffered_samples <= 0:
                self._buffered_samples = 0
                self._playing.clear()
                self._priming = True  # re-arm so the next utterance also gets a prebuffer

        # Mirror output frames to reference callback or fallback queue
        ref_chunk = outdata[:, 0].copy()
        if self._reference_callback is not None:
            try:
                self._reference_callback(ref_chunk)
            except Exception:
                pass
        else:
            try:
                self._reference_queue.put_nowait(ref_chunk)
            except Exception:
                pass

    def poll_reference(self) -> Optional[np.ndarray]:
        try:
            return self._reference_queue.get_nowait()
        except queue.Empty:
            return None

    def enqueue(self, audio_array: np.ndarray) -> None:
        """Append a chunk of int16 PCM audio to the continuous playback buffer."""
        with self._lock:
            self._chunks.append(audio_array)
            self._buffered_samples += len(audio_array)
            self._playing.set()

    def is_playing(self) -> bool:
        return self._playing.is_set()

    def buffered_seconds(self) -> float:
        """Seconds of audio currently queued but not yet played — used to
        throttle text reveal when SYNC_TEXT_TO_SPEECH is enabled."""
        with self._lock:
            return self._buffered_samples / self._samplerate

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()
