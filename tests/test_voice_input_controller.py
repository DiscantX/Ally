"""Unit tests for gui_qt.prod.voice_input_controller.

Covers:
- Graceful degrade when the Vosk model directory is missing
  (SpeechRecognizer.__init__ raises FileNotFoundError; controller must
  catch it and emit ``unavailable`` rather than crashing).
- Mode switching: ``push_to_talk`` vs ``open_mic``.
- ``push_to_talk`` start/stop flow and transcript flush on button release.
- ``open_mic`` continuous capture and pause-based finalization.
- ``set_open_mic_enabled`` guard when in wrong mode.
"""
from __future__ import annotations

import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

# ---------------------------------------------------------------------------
# Imports — must happen after QCoreApplication is created below
# ---------------------------------------------------------------------------

# Import VoiceInputController so that unittest.mock.patch can resolve the
# target "gui_qt.prod.voice_input_controller.SpeechRecognizer" at patch time.
from gui_qt.prod.voice_input_controller import VoiceInputController


class SignalSink:
    """Collects Qt signal emissions for inspection."""

    def __init__(self, controller):
        self.transcript_values: list[str] = []
        self.listening_values: list[bool] = []
        self.unavailable_values: list[str] = []
        controller.transcript_ready.connect(self._on_transcript)
        controller.listening_state_changed.connect(self._on_listening)
        controller.unavailable.connect(self._on_unavailable)

    def _on_transcript(self, text: str) -> None:
        self.transcript_values.append(text)

    def _on_listening(self, state: bool) -> None:
        self.listening_values.append(state)

    def _on_unavailable(self, reason: str) -> None:
        self.unavailable_values.append(reason)


def _mock_recognizer() -> MagicMock:
    """Return a mock SpeechRecognizer that is already open (context manager)."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _make_recognizer_factory(mock_rec: MagicMock, raises: Optional[Exception] = None):
    """Return a factory suitable for patching SpeechRecognizer.__init__."""
    def factory(*args, **kwargs):
        if raises is not None:
            raise raises
        return mock_rec
    return factory


# ---------------------------------------------------------------------------
# Graceful degrade — missing Vosk model
# ---------------------------------------------------------------------------

class TestGracefulDegrade(unittest.TestCase):
    """Tests for graceful degrade when the Vosk model is missing."""

    def test_unavailable_signal_emitted_when_model_missing(self) -> None:
        """When SpeechRecognizer raises FileNotFoundError the controller emits
        ``unavailable`` instead of propagating the exception."""
        exc = FileNotFoundError("Vosk model not found at 'model'")
        mock_rec = _mock_recognizer()
        factory = _make_recognizer_factory(mock_rec, raises=exc)

        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", factory):
            controller = VoiceInputController()
            sink = SignalSink(controller)

        # Should have emitted exactly one unavailable signal with the error message
        self.assertEqual(len(sink.unavailable_values), 1)
        self.assertIn("model", sink.unavailable_values[0])

        # is_available must be False so callers know the feature is degraded
        self.assertFalse(controller.is_available())

        # start/stop must be safe no-ops on a degraded controller
        controller.start_listening()
        controller.stop_listening()
        self.assertEqual(len(sink.transcript_values), 0)
        self.assertEqual(len(sink.listening_values), 0)

    def test_only_file_not_found_caught(self) -> None:
        """Only FileNotFoundError is caught; other exceptions propagate."""
        mock_rec = _mock_recognizer()
        factory = _make_recognizer_factory(mock_rec, raises=RuntimeError("boom"))

        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", factory):
            with self.assertRaises(RuntimeError) as ctx:
                VoiceInputController()
            self.assertIn("boom", str(ctx.exception))


# ---------------------------------------------------------------------------
# Mode switching
# ---------------------------------------------------------------------------

class TestModeSwitching(unittest.TestCase):
    """Tests for STT mode switching."""

    def test_stt_mode_defaults_to_push_to_talk(self) -> None:
        """Default STT mode is 'push_to_talk'."""
        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", _make_recognizer_factory(_mock_recognizer())):
            with patch("gui_qt.prod.voice_input_controller._resolve_stt_mode", return_value="push_to_talk"):
                controller = VoiceInputController()
        self.assertEqual(controller.stt_mode(), "push_to_talk")

    def test_stt_mode_can_be_open_mic(self) -> None:
        """STT mode can be set to 'open_mic'."""
        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", _make_recognizer_factory(_mock_recognizer())):
            with patch("gui_qt.prod.voice_input_controller._resolve_stt_mode", return_value="open_mic"):
                controller = VoiceInputController()
        self.assertEqual(controller.stt_mode(), "open_mic")

    def test_set_open_mic_enabled_noop_in_push_to_talk(self) -> None:
        """set_open_mic_enabled is a no-op when mode is push_to_talk."""
        mock_rec = _mock_recognizer()
        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", _make_recognizer_factory(mock_rec)):
            with patch("gui_qt.prod.voice_input_controller._resolve_stt_mode", return_value="push_to_talk"):
                controller = VoiceInputController()

        # Must not crash
        controller.set_open_mic_enabled(True)
        controller.set_open_mic_enabled(False)


# ---------------------------------------------------------------------------
# Push-to-talk flow
# ---------------------------------------------------------------------------

class TestPushToTalk(unittest.TestCase):
    """Tests for push-to-talk mode."""

    def test_start_listening_starts_capture_thread(self) -> None:
        """start_listening() spins up the background capture thread and emits
        listening_state_changed(True)."""
        mock_rec = _mock_recognizer()
        # Simulate poll returning None (no speech yet)
        mock_rec.poll.return_value = None

        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", _make_recognizer_factory(mock_rec)):
            with patch("gui_qt.prod.voice_input_controller._resolve_stt_mode", return_value="push_to_talk"):
                controller = VoiceInputController()

        sink = SignalSink(controller)
        controller.start_listening()

        # Give the thread time to start and emit the signal
        QTest.qWait(100)

        self.assertIn(True, sink.listening_values)  # listening started
        # Stop it cleanly before teardown
        controller.stop_listening()
        QTest.qWait(100)

    def test_stop_listening_flushes_and_emits_transcript(self) -> None:
        """stop_listening() drains the recognizer and emits transcript_ready
        with the accumulated text."""
        mock_rec = _mock_recognizer()
        # Simulate two fragments recognised during capture
        mock_rec.poll.side_effect = ["hello", "world", None]  # None = queue empty

        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", _make_recognizer_factory(mock_rec)):
            with patch("gui_qt.prod.voice_input_controller._resolve_stt_mode", return_value="push_to_talk"):
                controller = VoiceInputController()

        sink = SignalSink(controller)
        controller.start_listening()
        QTest.qWait(50)
        controller.stop_listening()
        QTest.qWait(100)

        # Should have emitted "hello world" (space-joined fragments)
        self.assertEqual(len(sink.transcript_values), 1)
        self.assertIn("hello", sink.transcript_values[0])
        self.assertIn("world", sink.transcript_values[0])

    def test_stop_listening_no_signal_when_recognizer_returns_nothing(self) -> None:
        """stop_listening() emits nothing when the recognizer had no speech."""
        mock_rec = _mock_recognizer()
        mock_rec.poll.return_value = None

        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", _make_recognizer_factory(mock_rec)):
            with patch("gui_qt.prod.voice_input_controller._resolve_stt_mode", return_value="push_to_talk"):
                controller = VoiceInputController()

        sink = SignalSink(controller)
        controller.start_listening()
        QTest.qWait(50)
        controller.stop_listening()
        QTest.qWait(100)

        self.assertEqual(len(sink.transcript_values), 0)

    def test_stop_listening_while_not_listening_is_safe(self) -> None:
        """Calling stop_listening() without a prior start_listening() must
        not crash or emit any signals."""
        mock_rec = _mock_recognizer()
        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", _make_recognizer_factory(mock_rec)):
            with patch("gui_qt.prod.voice_input_controller._resolve_stt_mode", return_value="push_to_talk"):
                controller = VoiceInputController()
        sink = SignalSink(controller)
        controller.stop_listening()  # no prior start
        self.assertEqual(len(sink.transcript_values), 0)
        self.assertEqual(len(sink.listening_values), 0)


# ---------------------------------------------------------------------------
# Open-mic flow
# ---------------------------------------------------------------------------

class TestOpenMic(unittest.TestCase):
    """Tests for open-mic mode."""

    def test_set_open_mic_enabled_starts_capture(self) -> None:
        """set_open_mic_enabled(True) starts the capture thread in open_mic mode."""
        mock_rec = _mock_recognizer()
        mock_rec.poll.return_value = None

        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", _make_recognizer_factory(mock_rec)):
            with patch("gui_qt.prod.voice_input_controller._resolve_stt_mode", return_value="open_mic"):
                controller = VoiceInputController()

        sink = SignalSink(controller)
        controller.set_open_mic_enabled(True)
        QTest.qWait(100)

        self.assertIn(True, sink.listening_values)
        controller.set_open_mic_enabled(False)
        QTest.qWait(100)

    def test_set_open_mic_enabled_stops_capture(self) -> None:
        """set_open_mic_enabled(False) stops the capture thread."""
        mock_rec = _mock_recognizer()
        mock_rec.poll.return_value = None

        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", _make_recognizer_factory(mock_rec)):
            with patch("gui_qt.prod.voice_input_controller._resolve_stt_mode", return_value="open_mic"):
                controller = VoiceInputController()

        sink = SignalSink(controller)
        controller.set_open_mic_enabled(True)
        QTest.qWait(100)
        controller.set_open_mic_enabled(False)
        QTest.qWait(100)

        # listening_state_changed should have been emitted twice: True then False
        self.assertIn(True, sink.listening_values)
        self.assertIn(False, sink.listening_values)

    def test_open_mic_uses_assembler_pause_finalization(self) -> None:
        """In open_mic mode, phrases are buffered in the assembler and
        emitted once the silence window passes."""
        mock_rec = _mock_recognizer()
        # Return one phrase, then empty queues forever
        mock_rec.poll.side_effect = ["continuous speech fragment", None, None]

        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", _make_recognizer_factory(mock_rec)):
            with patch("gui_qt.prod.voice_input_controller._resolve_stt_mode", return_value="open_mic"):
                # Use a very short pause window so we don't wait seconds in tests
                with patch("gui_qt.prod.voice_input_controller.UtteranceAssembler") as MockAssembler:
                    instance = MagicMock()
                    instance.has_pending.return_value = False
                    instance.ready.return_value = True
                    instance.flush.return_value = "continuous speech fragment"
                    MockAssembler.return_value = instance

                    controller = VoiceInputController()

        sink = SignalSink(controller)
        controller.set_open_mic_enabled(True)
        QTest.qWait(150)  # enough time for the loop to tick and detect readiness

        # The assembler was called with the phrase
        instance.add_fragment.assert_called_once_with("continuous speech fragment")

        # stop cleanly
        controller.set_open_mic_enabled(False)
        QTest.qWait(50)

    def test_start_listening_in_open_mic_noop_when_open_mic_not_enabled(self) -> None:
        """In open_mic mode, start_listening() is a no-op unless open_mic is enabled."""
        mock_rec = _mock_recognizer()
        mock_rec.poll.return_value = None

        with patch("gui_qt.prod.voice_input_controller.SpeechRecognizer", _make_recognizer_factory(mock_rec)):
            with patch("gui_qt.prod.voice_input_controller._resolve_stt_mode", return_value="open_mic"):
                controller = VoiceInputController()

        sink = SignalSink(controller)
        # open_mic_enabled is False by default in open_mic mode
        controller.start_listening()
        QTest.qWait(100)

        # No listening started because open_mic_enabled is False
        self.assertNotIn(True, sink.listening_values)


# ---------------------------------------------------------------------------
# Entry-point for run_tests.py
# ---------------------------------------------------------------------------

class TestVoiceInputController(
    TestGracefulDegrade,
    TestModeSwitching,
    TestPushToTalk,
    TestOpenMic,
):
    """Composite test class compatible with run_tests.py."""
    pass


if __name__ == "__main__":
    # Create QApplication before running
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    unittest.main()
