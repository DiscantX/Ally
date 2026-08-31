"""Output / Logs dev dock panel with REGISTRY channel dropdown filtering.
"""
from typing import Optional, Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QTextEdit, QLabel
from gui_qt.theming.theme import NEUTRAL_CONTENT_THEME
from infrastructure.logger.logger import subscribe, unsubscribe, LogEntry, REGISTRY


class OutputPanel(QWidget):
    """Dock panel displaying filtered log output with channel selection.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__outputPanel")
        self._all_entries: list[LogEntry] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Channel:", self))
        self._combo = QComboBox(self)
        self._combo.setObjectName("devDock__outputChannelCombo")
        self._combo.addItem("All")
        for v in REGISTRY.values():
            self._combo.addItem(v["name"])
        self._combo.currentTextChanged.connect(self._refresh_display)
        top_bar.addWidget(self._combo)
        top_bar.addStretch(1)
        layout.addLayout(top_bar)

        self._text = QTextEdit(self)
        self._text.setObjectName("devDock__outputText")
        self._text.setReadOnly(True)
        self._text.setStyleSheet(f"background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; color: {NEUTRAL_CONTENT_THEME.fg_primary}; font-family: monospace; font-size: 11px;")
        layout.addWidget(self._text)

        subscribe(self._on_log_entry)

    def _on_log_entry(self, entry: LogEntry) -> None:
        """Receives log entry and appends if matches current channel filter.
        """
        self._all_entries.append(entry)
        if len(self._all_entries) > 1000:
            self._all_entries.pop(0)
        self._append_entry_if_matches(entry)

    def _append_entry_if_matches(self, entry: LogEntry) -> None:
        """Appends log entry to text edit if channel matches filter.
        """
        channel = self._combo.currentText()
        if channel == "All" or entry.brain_name.lower() == channel.lower():
            line = f"[{entry.brain_name}] {entry.message}"
            self._text.append(line)

    def _refresh_display(self) -> None:
        """Refreshes text view based on selected channel filter.
        """
        channel = self._combo.currentText()
        lines = []
        for entry in self._all_entries:
            if channel == "All" or entry.brain_name.lower() == channel.lower():
                lines.append(f"[{entry.brain_name}] {entry.message}")
        self._text.setPlainText("\n".join(lines))

    def closeEvent(self, event: Any) -> None:
        """Unsubscribes logger on close.
        """
        unsubscribe(self._on_log_entry)
        super().closeEvent(event)
