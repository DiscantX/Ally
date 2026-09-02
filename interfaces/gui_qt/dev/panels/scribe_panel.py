"""Scribe pretty JSON dev dock panel.
"""
from typing import Optional, Any
import json
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from interfaces.gui_qt.theming.theme import NEUTRAL_CONTENT_THEME


class ScribePanel(QWidget):
    """Dock panel displaying Scribe output as pretty-printed JSON.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__scribePanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._text = QTextEdit(self)
        self._text.setObjectName("devDock__scribeText")
        self._text.setReadOnly(True)
        self._text.setStyleSheet(f"background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; color: {NEUTRAL_CONTENT_THEME.fg_primary}; font-family: monospace; font-size: 11px;")
        self._text.setPlainText("Awaiting Scribe output...")
        layout.addWidget(self._text)

    def handle_scribe_output(self, output: Any) -> None:
        """Receives ScribeOutput (or None) and displays pretty JSON.
        """
        if output is None:
            self._text.setPlainText("(Scribe skipped this turn)")
            return
        try:
            if hasattr(output, "model_dump_json"):
                json_str = output.model_dump_json(indent=2)
            elif hasattr(output, "dict"):
                json_str = json.dumps(output.dict(), indent=2)
            else:
                json_str = json.dumps(output, indent=2, default=str)
            self._text.setPlainText(json_str)
        except Exception as e:
            self._text.setPlainText(f"Error formatting Scribe output: {e}\nRaw: {output}")
