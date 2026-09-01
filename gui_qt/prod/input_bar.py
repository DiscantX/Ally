"""Input bar component with chat/feedback mode toggle, enter-to-send, and expand chevron.
"""
from typing import Optional, Literal
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QTextEdit,
    QPushButton,
    QToolButton,
)
from gui_qt.theming.theme import Theme


class EnterKeyTextEdit(QTextEdit):
    """Custom QTextEdit that intercepts Enter to trigger send and Shift+Enter for newline.
    """
    returnPressed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.returnPressed.emit()
                event.accept()
        else:
            super().keyPressEvent(event)


class InputBar(QWidget):
    """Input bar widget for sending messages or feedback, with mode toggle and expand chevron.
    """
    message_sent = Signal(str, str)  # text, mode ("chat" or "feedback")
    expand_toggled = Signal(bool)    # expanded state

    # Voice input signals
    mic_pressed = Signal()          # push-to-talk: button pressed
    mic_released = Signal()         # push-to-talk: button released
    mic_toggled = Signal(bool)      # open_mic: button toggled (True=on, False=off)

    def __init__(
        self,
        theme: Theme,
        stt_mode: Literal["push_to_talk", "open_mic"] = "push_to_talk",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._theme = theme
        self._mode: Literal["chat", "feedback"] = "chat"
        self._expanded = False
        self._stt_mode = stt_mode

        self.setObjectName("inputBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Mic button (voice input) — inserted as leftmost widget
        self._mic_btn = QToolButton(self)
        self._mic_btn.setObjectName("inputBar__micButton")
        self._mic_btn.setText("🎤")
        self._mic_btn.setToolTip("Voice Input")

        if self._stt_mode == "push_to_talk":
            # push-to_talk: non-checkable, pressed/released signals
            self._mic_btn.pressed.connect(self._on_mic_pressed)
            self._mic_btn.released.connect(self._on_mic_released)
        else:
            # open_mic: checkable, toggled signal
            self._mic_btn.setCheckable(True)
            self._mic_btn.toggled.connect(self._on_mic_toggled)

        layout.addWidget(self._mic_btn)

        # Mode toggle button
        self._mode_btn = QToolButton(self)
        self._mode_btn.setObjectName("inputBar__modeToggle")
        self._mode_btn.setToolTip("Toggle Mode: Chat (C) / Feedback (F)")
        self._mode_btn.setText("💬")
        self._mode_btn.setCheckable(True)
        self._mode_btn.clicked.connect(self._on_mode_clicked)
        layout.addWidget(self._mode_btn)

        # Text edit
        self._text_edit = EnterKeyTextEdit(self)
        self._text_edit.setObjectName("inputBar__textEdit")
        self._text_edit.setPlaceholderText("Type message to Ally... (Enter to send, Shift+Enter for newline)")
        self._text_edit.setFixedHeight(36)
        self._text_edit.returnPressed.connect(self._handle_send)
        layout.addWidget(self._text_edit)

        # Send button
        self._send_btn = QPushButton("Send", self)
        self._send_btn.setObjectName("inputBar__sendButton")
        self._send_btn.setFixedWidth(60)
        self._send_btn.clicked.connect(self._handle_send)
        layout.addWidget(self._send_btn)

        # Expand chevron button
        self._expand_btn = QToolButton(self)
        self._expand_btn.setObjectName("inputBar__expandButton")
        self._expand_btn.setToolTip("Expand / Collapse Feed")
        self._expand_btn.setText("⌃")
        self._expand_btn.setCheckable(True)
        self._expand_btn.clicked.connect(self._on_expand_clicked)
        layout.addWidget(self._expand_btn)

    # -------------------------------------------------------------------------
    # Voice input slots and helpers
    # -------------------------------------------------------------------------

    def _on_mic_pressed(self) -> None:
        """Handle mic button press (push-to-talk mode).
        """
        self.mic_pressed.emit()

    def _on_mic_released(self) -> None:
        """Handle mic button release (push-to-talk mode).
        """
        self.mic_released.emit()

    def _on_mic_toggled(self, checked: bool) -> None:
        """Handle mic button toggle (open-mic mode).
        """
        self.mic_toggled.emit(checked)

    def on_transcript_ready(self, text: str) -> None:
        """Public slot: populate text field with transcript and send it.

        Called by VoiceInputController when a voice transcript is ready.
        """
        self._text_edit.setPlainText(text)
        self._handle_send()

    def on_listening_state_changed(self, listening: bool) -> None:
        """Public slot: update mic button appearance when listening state changes.

        Swaps mic button text between 🎤 (idle) and 🔴 (listening).
        """
        if listening:
            self._mic_btn.setText("🔴")
            self._mic_btn.setToolTip("Listening... (click to stop)")
        else:
            self._mic_btn.setText("🎤")
            self._mic_btn.setToolTip("Voice Input")

    def set_mic_available(self, available: bool, reason: str = "") -> None:
        """Public method: enable or disable the mic button.

        When unavailable, the button is disabled and the tooltip shows the reason.
        """
        self._mic_btn.setEnabled(available)
        if available:
            self._mic_btn.setToolTip("Voice Input")
        else:
            self._mic_btn.setToolTip(f"Voice Input Unavailable: {reason}" if reason else "Voice Input Unavailable")

    # -------------------------------------------------------------------------
    # Mode and send handlers
    # -------------------------------------------------------------------------

    def _on_mode_clicked(self) -> None:
        """Switches mode between chat and feedback.
        """
        if self._mode == "chat":
            self._mode = "feedback"
            self._mode_btn.setText("⚡")
            self._mode_btn.setToolTip("Mode: Feedback (Direct Correction)")
            self._text_edit.setPlaceholderText("Provide direct feedback / correction to Ally...")
        else:
            self._mode = "chat"
            self._mode_btn.setText("💬")
            self._mode_btn.setToolTip("Mode: Chat")
            self._text_edit.setPlaceholderText("Type message to Ally... (Enter to send, Shift+Enter for newline)")

    def _on_expand_clicked(self) -> None:
        """Toggles expanded state.
        """
        self._expanded = self._expand_btn.isChecked()
        self._expand_btn.setText("⌄" if self._expanded else "⌃")
        self.expand_toggled.emit(self._expanded)

    def _handle_send(self) -> None:
        """Sends the current text content.
        """
        text = self._text_edit.toPlainText().strip()
        if text:
            self.message_sent.emit(text, self._mode)
            self._text_edit.clear()

    def get_mode(self) -> str:
        """Returns current mode ('chat' or 'feedback').
        """
        return self._mode
