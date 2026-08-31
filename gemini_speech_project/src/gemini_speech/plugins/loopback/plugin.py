"""
LoopbackPluginManager class that manages capture, AEC filtering, reference polling,
and streaming loopback audio to the Gemini Live session.
"""

import asyncio
import numpy as np
import scipy.signal as signal
from google.genai import types
from typing import Optional

from .loopback import SystemLoopbackCapture
from .filter import EchoCancellationFilter


class LoopbackPluginManager:
    """Manages system audio capture, echo cancellation filtering, and WebSocket streaming to Gemini Live."""

    def __init__(self, target_sample_rate: int = 16000):
        self._target_sample_rate = target_sample_rate
        self._capture = SystemLoopbackCapture(target_sample_rate=target_sample_rate)
        self._filter_engine = EchoCancellationFilter(sample_rate=target_sample_rate, channels=1)
        self._streaming_task: Optional[asyncio.Task] = None
        self._running = False

    def get_reference_callback(self):
        """Returns a callback function to plug into AudioPlayer for real-time reference tracking."""
        def callback(ref_chunk: np.ndarray):
            if ref_chunk is not None and len(ref_chunk) > 0:
                if len(ref_chunk.shape) > 1:
                    ref_mono = ref_chunk.mean(axis=1)
                else:
                    ref_mono = ref_chunk
                self._filter_engine.analyze_reference(ref_mono.astype(np.int16))
        return callback

    def start(self) -> None:
        """Start the system loopback capture stream."""
        self._capture.start()
        self._running = True

    def stop(self) -> None:
        """Stop the system loopback capture stream."""
        self._running = False
        self._capture.stop()

    def level(self) -> float:
        """Return current loopback loudness level (0.0 to 1.0) for visual meters."""
        return self._capture.level()

    async def stream_loop(self, session, player) -> None:
        """Continuous background task polling captured game audio, applying AEC, and sending to Gemini Live."""
        buffer = np.array([], dtype=np.int16)
        chunk_size_samples = 320  # 20ms micro-bursts at 16kHz

        while self._running:
            # Poll playback reference from player if reference_callback wasn't used directly
            ref_chunk = player.poll_reference()
            if ref_chunk is not None:
                if len(ref_chunk.shape) > 1:
                    ref_mono = ref_chunk.mean(axis=1)
                else:
                    ref_mono = ref_chunk
                if player._samplerate != self._target_sample_rate:
                    num_samples = int(len(ref_mono) * self._target_sample_rate / player._samplerate)
                    ref_mono = signal.resample(ref_mono, num_samples)
                self._filter_engine.analyze_reference(ref_mono.astype(np.int16))

            # Poll loopback audio chunk, downmix stereo to mono, resample, and apply AEC
            data = self._capture.poll_audio()
            if data:
                try:
                    audio_array = np.frombuffer(data, dtype=np.int16)
                    if self._capture._actual_channels > 1:
                        audio_array = audio_array.reshape(-1, self._capture._actual_channels).mean(axis=1)

                    if self._capture._actual_sample_rate != self._target_sample_rate:
                        num_samples = int(len(audio_array) * self._target_sample_rate / self._capture._actual_sample_rate)
                        audio_array = signal.resample(audio_array, num_samples)

                    cleaned_array = self._filter_engine.process_stream(audio_array.astype(np.int16))
                    buffer = np.concatenate((buffer, cleaned_array.astype(np.int16)))

                    # Dispatch in strict 20ms micro-bursts (320 samples each)
                    while len(buffer) >= chunk_size_samples:
                        packet = buffer[:chunk_size_samples]
                        buffer = buffer[chunk_size_samples:]
                        packet_bytes = packet.tobytes()

                        await session.send(
                            input=types.LiveClientRealtimeInput(
                                audio=types.Blob(
                                    data=packet_bytes,
                                    mime_type=f"audio/pcm;rate={self._target_sample_rate}"
                                )
                            )
                        )
                except Exception as e:
                    import sys
                    print(f"Error streaming filtered loopback audio: {e}", file=sys.stderr)
            await asyncio.sleep(0.005)
