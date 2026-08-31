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

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme = theme
        self._mode: Literal["chat", "feedback"] = "chat"
        self._expanded = False

        self.setObjectName("inputBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

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
