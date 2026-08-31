"""
Windows WASAPI loopback audio capture module using pyaudiowpatch.
Provides device discovery, thread-safe streaming, and diagnostic WAV recording for Slice 4.1.
"""

import sys
import time
import wave
import queue
import threading
import numpy as np
from typing import Optional
import pyaudiowpatch as pyaudio


class SystemLoopbackCapture:
    """Captures system audio output (WASAPI loopback) using pyaudiowpatch."""

    def __init__(self, target_sample_rate: int = 16000, chunk_size: int = 1024):
        self._target_sample_rate = target_sample_rate
        self._chunk_size = chunk_size
        self._audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self._level = 0.0  # crude cosmetic loudness for terminal meter
        self._level_lock = threading.Lock()
        self._pyaudio = None
        self._stream = None
        self._device_info = None
        self._actual_sample_rate = 44100
        self._actual_channels = 2

    def __enter__(self) -> "SystemLoopbackCapture":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def start(self) -> None:
        self._pyaudio = pyaudio.PyAudio()
        try:
            wasapi_info = self._pyaudio.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError:
            print("Error: WASAPI host API not found on this system.", file=sys.stderr)
            self._pyaudio.terminate()
            raise RuntimeError("WASAPI host API not found.")

        default_output_idx = wasapi_info["defaultOutputDevice"]
        default_output = self._pyaudio.get_device_info_by_index(default_output_idx)
        print(f"Default multimedia output device: {default_output['name']}")

        loopback_info = None
        try:
            for loop in self._pyaudio.get_loopback_device_info_generator():
                if default_output["name"] in loop["name"] or loop.get("isLoopbackDevice"):
                    loopback_info = loop
                    break
        except Exception as e:
            print(f"Warning during loopback generator scan: {e}", file=sys.stderr)

        if not loopback_info:
            try:
                for loop in self._pyaudio.get_loopback_device_info_generator():
                    loopback_info = loop
                    break
            except Exception:
                pass

        if not loopback_info:
            self._pyaudio.terminate()
            raise RuntimeError("Could not locate any WASAPI loopback audio device.")

        self._device_info = loopback_info
        self._actual_sample_rate = int(loopback_info["defaultSampleRate"])
        self._actual_channels = int(loopback_info["maxInputChannels"])
        print(f"Selected loopback device: {loopback_info['name']} (Sample Rate: {self._actual_sample_rate}Hz, Channels: {self._actual_channels})")

        def callback(in_data, frame_count, time_info, status):
            if status:
                print(status, file=sys.stderr)
            try:
                samples = np.frombuffer(in_data, dtype=np.int16)
                if len(samples):
                    level = min(1.0, float(np.abs(samples).mean()) / 2000.0)
                    with self._level_lock:
                        self._level = level
            except Exception:
                pass
            self._audio_queue.put(in_data)
            return (None, pyaudio.paContinue)

        self._stream = self._pyaudio.open(
            format=pyaudio.paInt16,
            channels=self._actual_channels,
            rate=self._actual_sample_rate,
            input=True,
            input_device_index=loopback_info["index"],
            frames_per_buffer=self._chunk_size,
            stream_callback=callback,
        )
        self._stream.start_stream()

    def stop(self) -> None:
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass
            self._pyaudio = None

    def poll_audio(self) -> Optional[bytes]:
        try:
            return self._audio_queue.get_nowait()
        except queue.Empty:
            return None

    def level(self) -> float:
        """Current loopback loudness, roughly 0.0–1.0, for the terminal meter."""
        with self._level_lock:
            return self._level


def record_diagnostic_wav(filepath: str = "loopback_test.wav", duration_seconds: float = 10.0) -> None:
    """Record system audio loopback to a diagnostic .wav file for Slice 4.1 verification."""
    print(f"\n=== Starting System Loopback Diagnostic Recording ({duration_seconds}s) ===")
    print("Play some audio or music on your desktop now to capture it...")

    with SystemLoopbackCapture() as capture:
        wf = wave.open(filepath, "wb")
        wf.setnchannels(capture._actual_channels)
        wf.setsampwidth(2)
        wf.setframerate(capture._actual_sample_rate)

        start_time = time.monotonic()
        chunks_recorded = 0
        while time.monotonic() - start_time < duration_seconds:
            data = capture.poll_audio()
            if data:
                wf.writeframes(data)
                chunks_recorded += 1
            else:
                time.sleep(0.005)

        wf.close()
    print(f"=== Recording Complete! Saved {chunks_recorded} audio chunks to `{filepath}` ===")


if __name__ == "__main__":
    record_diagnostic_wav()
