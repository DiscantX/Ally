"""OCR and Screen Classification dev dock panel.
"""
from typing import Optional, Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel
from gui_qt.theming.theme import NEUTRAL_CONTENT_THEME


class OcrPanel(QWidget):
    """Dock panel showing screen classification, confidence, OCR facts, and skip reasons.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__ocrPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._text = QTextEdit(self)
        self._text.setObjectName("devDock__ocrText")
        self._text.setReadOnly(True)
        self._text.setStyleSheet(f"background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; color: {NEUTRAL_CONTENT_THEME.fg_primary}; font-family: monospace; font-size: 11px;")
        self._text.setPlainText("Awaiting OCR / screen classification result...")
        layout.addWidget(self._text)

    def handle_ocr_result(self, payload: dict[str, Any]) -> None:
        """Formats and displays OCR / screen classification payload.
        """
        if not isinstance(payload, dict):
            self._text.setPlainText(str(payload))
            return
        lines = [
            f"Screen Name:     {payload.get('screen_name', 'unknown')} ({payload.get('confidence', 0.0):.2f})",
            f"Is Draft Match:  {payload.get('is_draft', False)}",
            f"Screen Category: {payload.get('screen_category', 'None')} / Skip Reason: {payload.get('skip_scribe_reason', 'none')}",
            f"\nConfirmed Facts ({len(payload.get('confirmed_facts', []))}):",
        ]
        for fact in payload.get("confirmed_facts", []):
            lines.append(f"  - {getattr(fact, 'key', 'key')}: {getattr(fact, 'value', 'val')} (source={getattr(fact, 'source', 'src')})")
        self._text.setPlainText("\n".join(lines))
