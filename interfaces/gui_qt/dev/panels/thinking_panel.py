"""Live thinking-stream dev dock panel.
"""
from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from interfaces.gui_qt.theming.theme import NEUTRAL_CONTENT_THEME


class ThinkingPanel(QWidget):
    """Dock panel displaying Ally's live streamed thinking-trace text.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__thinkingPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._text = QTextEdit(self)
        self._text.setObjectName("devDock__thinkingText")
        self._text.setReadOnly(True)
        self._text.setProperty("themed", "devPanelTextItalic")
        self._text.style().unpolish(self._text)
        self._text.style().polish(self._text)
        self._text.setPlainText("Awaiting thinking stream...")
        layout.addWidget(self._text)

    def set_active_theme(self, theme: Theme) -> None:
        """Sets active theme.
        """
        pass

    def handle_thinking_begin(self) -> None:
        """Clears the panel at the start of a new thinking stream.
        """
        self._text.setPlainText("")

    def handle_thinking_chunk(self, chunk: str) -> None:
        """Appends an incoming thinking-stream text chunk.
        """
        cursor = self._text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._text.setTextCursor(cursor)
        self._text.insertPlainText(chunk)

    def handle_thinking_reset(self) -> None:
        """Clears partial thinking text on a mid-stream retry.
        """
        self._text.setPlainText("")

    def handle_thinking_finalize(self) -> None:
        """No-op hook for stream completion -- kept for symmetry with
        the other stream lifecycle handlers and as a seam for a future
        'done thinking' visual state.
        """
        pass
