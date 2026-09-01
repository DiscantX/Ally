"""Voice output controller: bridges AllyCore chat-stream events to TTS + AudioPlayer.

This plain-Python class (no Qt dependency) listens on AllyCore's existing EventHooks
and synthesizes spoken audio for each incoming chat-stream chunk or finalized text.

Owned by AllyCore (constructed from main.py in Phase 7). Additive to AllyCore —
no changes required to brain/reasoning/core.py.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Optional

import numpy as np

from infrastructure.logger import log
from infrastructure.tts.base_provider import TTSProvider, SynthesizedAudio
from infrastructure.tts.audio_player import AudioPlayer

if TYPE_CHECKING:
    from brain.reasoning.core import AllyCore


MODULE_NAME = "VoiceOutputController"


class VoiceOutputController:
    """Bridges chat-stream events to TTS synthesis and audio playback.

    Listens on AllyCore's on_chat_stream_* hooks and produces spoken audio
    for each incoming text chunk. Supports both streaming and non-streaming
    TTS providers, using synthesize_stream() when available for lower latency.

    The controller is disabled by default and must be explicitly enabled via
    set_enabled(True) to begin synthesis.

    On on_chat_stream_reset (mid-stream retry): any in-flight synthesis is
    cancelled and already-queued audio is cleared via audio_player.clear_pending().

    All work triggered from EventHook.emit() callbacks is wrapped in try/except
    and logged on failure — never raises.
    """

    def __init__(
        self,
        tts_provider: TTSProvider,
        audio_player: AudioPlayer,
        enabled: bool = False,
    ) -> None:
        """Initialize the voice output controller.

        Args:
            tts_provider: TTS provider for speech synthesis. Must implement
                TTSProvider interface (supports both synthesize and synthesize_stream).
            audio_player: AudioPlayer instance for output playback.
            enabled: Whether voice output is initially enabled. Defaults to False.
        """
        self._tts_provider = tts_provider
        self._audio_player = audio_player
        self._enabled = enabled

        # Text buffer for accumulating chunks before synthesis
        self._buffer: list[str] = []
        self._buffer_lock = threading.Lock()

        # Flag to track in-flight synthesis for cancellation on reset
        self._cancel_synthesis = threading.Event()

        # Bound callbacks (kept for potential disconnect later)
        self._on_chunk_handler: Optional[callable] = None
        self._on_finalize_handler: Optional[callable] = None
        self._on_reset_handler: Optional[callable] = None

        log(
            "{}: Initialized (enabled={}, streaming_tts={})",
            MODULE_NAME,
            enabled,
            tts_provider.supports_streaming,
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable voice output.

        When disabled, no synthesis work is performed regardless of incoming
        chat-stream events.

        Args:
            enabled: True to enable voice output, False to disable.
        """
        if self._enabled == enabled:
            return

        was_enabled = self._enabled
        self._enabled = enabled
        log("{}: Voice output {}", MODULE_NAME, "enabled" if enabled else "disabled")

        # If disabling while something is playing, optionally clear it
        if was_enabled and not enabled:
            # Clear any pending audio when disabled
            try:
                self._audio_player.clear_pending()
            except Exception as exc:
                log("{}: Error clearing audio on disable: {}", MODULE_NAME, exc, level="warning")

    def is_enabled(self) -> bool:
        """Return whether voice output is currently enabled."""
        return self._enabled

    def attach(self, core: "AllyCore") -> None:
        """Subscribe to AllyCore chat-stream event hooks.

        Subscribes to:
          - core.on_chat_stream_chunk
          - core.on_chat_stream_finalize
          - core.on_chat_stream_reset

        Does NOT subscribe to on_analysis_stream_* hooks (explicitly out of scope).

        Args:
            core: AllyCore instance to subscribe to.
        """
        def on_chunk(text: str) -> None:
            """Handle incoming chat-stream text chunk."""
            try:
                if not self._enabled:
                    return
                self._handle_chunk(text)
            except Exception as exc:
                log("{}: Error in on_chat_stream_chunk handler: {}", MODULE_NAME, exc, level="error")

        def on_finalize(text: str) -> None:
            """Handle finalized chat-stream text."""
            try:
                if not self._enabled:
                    return
                self._handle_finalize(text)
            except Exception as exc:
                log("{}: Error in on_chat_stream_finalize handler: {}", MODULE_NAME, exc, level="error")

        def on_reset() -> None:
            """Handle mid-stream retry (reset)."""
            try:
                self._handle_reset()
            except Exception as exc:
                log("{}: Error in on_chat_stream_reset handler: {}", MODULE_NAME, exc, level="error")

        self._on_chunk_handler = on_chunk
        self._on_finalize_handler = on_finalize
        self._on_reset_handler = on_reset

        core.on_chat_stream_chunk.connect(on_chunk)
        core.on_chat_stream_finalize.connect(on_finalize)
        core.on_chat_stream_reset.connect(on_reset)

        log("{}: Attached to AllyCore chat-stream hooks", MODULE_NAME)

    def detach(self, core: "AllyCore") -> None:
        """Unsubscribe from AllyCore event hooks.

        Args:
            core: AllyCore instance to unsubscribe from.
        """
        if self._on_chunk_handler is not None:
            core.on_chat_stream_chunk.disconnect(self._on_chunk_handler)
        if self._on_finalize_handler is not None:
            core.on_chat_stream_finalize.disconnect(self._on_finalize_handler)
        if self._on_reset_handler is not None:
            core.on_chat_stream_reset.disconnect(self._on_reset_handler)

        self._on_chunk_handler = None
        self._on_finalize_handler = None
        self._on_reset_handler = None

        log("{}: Detached from AllyCore chat-stream hooks", MODULE_NAME)

    # -------------------------------------------------------------------------
    # Internal handlers
    # -------------------------------------------------------------------------

    def _handle_chunk(self, text: str) -> None:
        """Handle an incoming chat-stream text chunk.

        Accumulates text in the buffer and triggers synthesis. For streaming
        TTS providers, immediately synthesizes each sentence as it's completed.
        For non-streaming providers, buffers text for final synthesis.

        Args:
            text: Incoming text chunk.
        """
        with self._buffer_lock:
            self._buffer.append(text)

        if self._tts_provider.supports_streaming:
            # For streaming TTS: try to synthesize each sentence as it appears
            # The base synthesize_stream already does naive sentence splitting
            self._synthesize_stream(text)
        # For non-streaming: wait for finalize

    def _handle_finalize(self, text: str) -> None:
        """Handle finalized chat-stream text.

        Synthesizes the full accumulated text and plays it. This is the main
        synthesis path for non-streaming TTS providers.

        Args:
            text: Finalized text (may be empty if no text was accumulated).
        """
        if not text and not self._buffer:
            return

        # Build full text from buffer
        with self._buffer_lock:
            if text:
                self._buffer.append(text)
            full_text = "".join(self._buffer)
            self._buffer.clear()

        if not full_text.strip():
            return

        log("{}: Finalizing synthesis for {} chars", MODULE_NAME, len(full_text))

        if self._tts_provider.supports_streaming:
            # Synthesize and play sentence-by-sentence
            self._synthesize_stream(full_text)
        else:
            # Single-shot synthesis
            self._synthesize_single(full_text)

    def _handle_reset(self) -> None:
        """Handle mid-stream retry (reset).

        Cancels any in-flight synthesis and clears the audio buffer.
        """
        log("{}: Stream reset received", MODULE_NAME)

        # Signal cancellation for any in-flight synthesis
        self._cancel_synthesis.set()

        # Clear the text buffer
        with self._buffer_lock:
            self._buffer.clear()

        # Clear queued audio (preserves current playback position)
        try:
            self._audio_player.clear_pending()
        except Exception as exc:
            log("{}: Error clearing audio on reset: {}", MODULE_NAME, exc, level="warning")

        # Reset the cancel flag for next synthesis
        self._cancel_synthesis.clear()

        log("{}: Reset complete", MODULE_NAME)

    # -------------------------------------------------------------------------
    # Synthesis helpers
    # -------------------------------------------------------------------------

    def _synthesize_stream(self, text: str) -> None:
        """Synthesize text using streaming TTS and enqueue audio chunks.

        Iterates over synthesize_stream() and enqueues each SynthesizedAudio
        chunk as it arrives. Respects cancellation via _cancel_synthesis.

        Args:
            text: Text to synthesize.
        """
        if not text.strip():
            return

        try:
            for audio_chunk in self._tts_provider.synthesize_stream(text):
                if self._cancel_synthesis.is_set():
                    log("{}: Synthesis cancelled", MODULE_NAME)
                    break
                self._enqueue_audio(audio_chunk)
        except Exception as exc:
            log("{}: Error in stream synthesis: {}", MODULE_NAME, exc, level="error")

    def _synthesize_single(self, text: str) -> None:
        """Synthesize text using single-shot TTS and enqueue audio.

        Calls synthesize() and enqueues the result. Respects cancellation.

        Args:
            text: Text to synthesize.
        """
        if not text.strip():
            return

        if self._cancel_synthesis.is_set():
            log("{}: Synthesis skipped (cancelled)", MODULE_NAME)
            return

        try:
            audio = self._tts_provider.synthesize(text)
            if not self._cancel_synthesis.is_set():
                self._enqueue_audio(audio)
        except Exception as exc:
            log("{}: Error in single synthesis: {}", MODULE_NAME, exc, level="error")

    def _enqueue_audio(self, audio: SynthesizedAudio) -> None:
        """Convert SynthesizedAudio to numpy array and enqueue for playback.

        Args:
            audio: SynthesizedAudio from TTS provider.
        """
        try:
            # Convert PCM bytes to numpy array (int16, mono)
            audio_array = np.frombuffer(
                audio.pcm_data,
                dtype=np.int16,
            )

            self._audio_player.enqueue(audio_array)
            log(
                "{}: Enqueued {:.2f}s of audio",
                MODULE_NAME,
                audio.duration_seconds,
            )
        except Exception as exc:
            log("{}: Error enqueueing audio: {}", MODULE_NAME, exc, level="error")
