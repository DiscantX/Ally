"""Thinking stub dev dock panel.
"""
from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from gui_qt.theming.theme import NEUTRAL_CONTENT_THEME


class ThinkingPanel(QWidget):
    """Stub dock panel for thinking trace inspection.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__thinkingPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        label = QLabel(
            "Pending research — whether Gemini's structured-output mode exposes thought "
            "summaries needs verification before this panel can be built.",
            self
        )
        label.setObjectName("devDock__thinkingLabel")
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {NEUTRAL_CONTENT_THEME.fg_primary}; background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; font-size: 12px; padding: 12px;")
        layout.addWidget(label)
