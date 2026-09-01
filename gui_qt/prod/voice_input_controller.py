"""
Qt-side glue for microphone voice input.

Owns a `SpeechRecognizer` (Vosk STT) and an `UtteranceAssembler`
(open-mic pause buffering). Runs audio capture on a plain daemon
thread and emits cross-thread-safe Qt signals for the GUI to consume.

Two modes (controlled by config["stt_mode"], default "push_to_talk"):

  push_to_talk  — capture begins on `start_listening()`, stops on
                  `stop_listening()`.  On stop, any accumulated
                  transcript is force-flushed and emitted if non-empty.

  open_mic      — capture runs continuously while the controller is
                  enabled.  `UtteranceAssembler` holds per-pause
                  fragments until a configurable silence window passes
                  before finalizing the full utterance.
"""
from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

from infrastructure.logger import log
from infrastructure.stt.assembler import UtteranceAssembler
from infrastructure.stt.recognizer import SpeechRecognizer

# `load_user_config` lives in storage/configs/config_manager.py which is
# created in a later phase of the speech work. Make the import tolerant.
try:
    from cabinet.configs.config_manager import load_user_config
except ImportError:
    load_user_config = None  # type: ignore[assignment]

MODULE_NAME = "VoiceInputController"

# ---------------------------------------------------------------------------
# Defaults (mirrors gemini_speech config defaults)
# ---------------------------------------------------------------------------
_DEFAULT_STT_MODE = "push_to_talk"


def _resolve_stt_mode() -> str:
    """Return the STT mode from user config, safe-falling back to default."""
    if load_user_config is None:
        return _DEFAULT_STT_MODE
    try:
        cfg = load_user_config() or {}
        speech = cfg.get("speech") or {}
        return str(speech.get("stt_mode") or _DEFAULT_STT_MODE).strip().lower()
    except Exception as exc:
        log("Could not load speech config for stt_mode, using default: {}", exc, level="warning")
        return _DEFAULT_STT_MODE


# ---------------------------------------------------------------------------
# VoiceInputController
# ---------------------------------------------------------------------------

class VoiceInputController(QObject):
    """
    Qt-side controller for microphone voice input.

    Signals (all cross-thread safe via Qt's signal-slot mechanism):
      transcript_ready  (str)          — finalized transcript text ready to send
      listening_state_changed (bool)    — for mic-button visual feedback
      unavailable        (str)           — human-readable reason the recognizer
                                          could not be initialised
    """

    # Qt signals — must be class-level and declared on a QObject subclass
    transcript_ready = Signal(str)
    listening_state_changed = Signal(bool)
    unavailable = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self._stt_mode = _resolve_stt_mode()
        self._open_mic_enabled = False   # only meaningful when _stt_mode == "open_mic"

        # Attempt to create the recognizer; emit unavailable rather than crashing
        self._recognizer: Optional[SpeechRecognizer] = None
        try:
            self._recognizer = SpeechRecognizer()
            self._assembler = UtteranceAssembler()
        except FileNotFoundError as exc:
            log(
                "VoiceInputController: SpeechRecognizer unavailable — {}",
                exc,
                level="error",
                module=MODULE_NAME,
            )
            self.unavailable.emit(str(exc))
            return  # fully degraded; all public methods become no-ops

        # Capture thread state
        self._capture_thread: Optional[threading.Thread] = None
        self._stop_capture = threading.Event()   # set to ask the thread to exit
        self._is_listening = False
        self._lock = threading.Lock()

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def is_available(self) -> bool:
        """True when the recognizer was successfully initialised."""
        return self._recognizer is not None

    def stt_mode(self) -> str:
        """Current STT mode ("push_to_talk" or "open_mic")."""
        return self._stt_mode

    def set_open_mic_enabled(self, enabled: bool) -> None:
        """
        Enable or disable open-mic mode.

        Only meaningful when ``stt_mode()`` is ``"open_mic"``.  When enabled,
        the capture thread will run continuously and finalise utterances
        based on pause-based silence rather than explicit start/stop calls.
        """
        if self._stt_mode != "open_mic":
            return
        with self._lock:
            was_running = self._is_listening
            self._open_mic_enabled = enabled
            if not enabled and was_running:
                self._stop_listening_internal()
            elif enabled and not was_running:
                self._start_listening_internal()

    def start_listening(self) -> None:
        """
        Begin microphone capture (push-to-talk: call on button press).

        In ``push_to_talk`` mode this starts the capture loop on the
        background thread.  In ``open_mic`` mode this is a no-op when
        open mic is already running; otherwise it starts capture if
        open mic is enabled.
        """
        if not self._recognizer:
            return
        with self._lock:
            if self._stt_mode == "push_to_talk":
                self._start_listening_internal()
            else:  # open_mic
                if self._open_mic_enabled and not self._is_listening:
                    self._start_listening_internal()

    def stop_listening(self) -> None:
        """
        End microphone capture and flush any accumulated transcript
        (push-to-talk: call on button release).

        On release the recognizer is force-flushed: all buffered audio is
        processed immediately and any resulting text is emitted as
        ``transcript_ready`` if non-empty.  The capture thread is stopped.
        """
        if not self._recognizer:
            return
        with self._lock:
            if self._stt_mode == "push_to_talk":
                self._stop_and_flush()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _start_listening_internal(self) -> None:
        if self._is_listening:
            return
        self._stop_capture.clear()
        self._is_listening = True
        self.listening_state_changed.emit(True)
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name="VoiceInputCapture",
            daemon=True,
        )
        self._capture_thread.start()

    def _stop_listening_internal(self) -> None:
        """Signal the capture thread to stop without emitting a flush."""
        if not self._is_listening:
            return
        self._stop_capture.set()
        self._is_listening = False
        self.listening_state_changed.emit(False)

    def _stop_and_flush(self) -> None:
        """
        Signal capture thread to stop, drain the recognizer, emit if non-empty.

        Called by ``stop_listening()`` (push-to-talk button release).
        """
        self._stop_listening_internal()
        # Give the capture thread a moment to notice the stop signal
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=0.5)
        self._flush_and_emit()

    def _flush_and_emit(self) -> None:
        """Force-process all buffered audio and emit the result."""
        if not self._recognizer:
            return
        # Drain all pending audio
        while True:
            phrase = self._recognizer.poll()
            if phrase is None:
                break
            if self._stt_mode == "open_mic":
                self._assembler.add_fragment(phrase)
        # In open_mic mode, also flush the assembler
        if self._stt_mode == "open_mic" and self._assembler.has_pending():
            self._assembler._last_fragment_time = None  # force-ready
        if self._assembler.has_pending():
            final_text = self._assembler.flush().strip()
            if final_text:
                self.transcript_ready.emit(final_text)

    def _capture_loop(self) -> None:
        """
        Background thread loop that polls the recognizer and routes output.

        In ``push_to_talk`` mode each finalized phrase is buffered until
        ``stop_listening()`` is called.

        In ``open_mic`` mode phrases are added to ``_assembler`` and a
        final utterance is emitted once the configured silence window passes.
        """
        assert self._recognizer is not None
        assert self._assembler is not None

        with self._recognizer:  # context manager starts/stops the stream
            while not self._stop_capture.wait(timeout=0.05):
                phrase = self._recognizer.poll()
                if phrase is None:
                    continue

                if self._stt_mode == "push_to_talk":
                    # Buffer for later flush-on-release
                    self._assembler.add_fragment(phrase)
                else:  # open_mic
                    self._assembler.add_fragment(phrase)
                    if self._assembler.ready():
                        final_text = self._assembler.flush().strip()
                        if final_text:
                            self.transcript_ready.emit(final_text)
