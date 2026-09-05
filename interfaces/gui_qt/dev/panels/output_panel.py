"""Logs dev dock panel with REGISTRY channel dropdown filtering.
"""
from typing import Optional, Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QTextEdit, QLabel
from interfaces.gui_qt.theming.theme import SLATE, SIGNAL, SYNTHWAVE
from theming.palettes import resolve_module_color
from infrastructure.logger.logger import LogEntry, REGISTRY
from interfaces.gui_qt.dev.qt_safe_logger import QtSafeLogSubscriber


class OutputPanel(QWidget):
    """Dock panel displaying filtered log output with channel selection.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__outputPanel")
        self._all_entries: list[LogEntry] = []
        self._active_theme_name: str = "Slate"
        self._themes = {"Slate": SLATE, "Signal": SIGNAL, "Synthwave": SYNTHWAVE}

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
        self._text.setProperty("themed", "devPanelText")
        self._text.style().unpolish(self._text)
        self._text.style().polish(self._text)
        layout.addWidget(self._text)

        self._qt_log_subscriber = QtSafeLogSubscriber(self._on_log_entry, self)

    def set_active_theme(self, theme_name: str) -> None:
        self._active_theme_name = theme_name
        self._refresh_display()

    def _format_entry_html(self, entry: LogEntry) -> str:
        theme = self._themes.get(self._active_theme_name, SLATE)
        mod_color = resolve_module_color(self._active_theme_name, entry.brain_name)
        level_lower = entry.level.lower()
        level_color = theme.log_level_colors.get(level_lower, theme.fg_primary)
        return f'<span style="color: {mod_color};">[{entry.brain_name}]</span> <span style="color: {level_color};">{entry.message}</span>'

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
            html = self._format_entry_html(entry)
            self._text.append(html)

    def _refresh_display(self) -> None:
        """Refreshes text view based on selected channel filter.
        """
        channel = self._combo.currentText()
        html_lines = []
        for entry in self._all_entries:
            if channel == "All" or entry.brain_name.lower() == channel.lower():
                html_lines.append(self._format_entry_html(entry))
        self._text.setHtml("<br>".join(html_lines))

    def closeEvent(self, event: Any) -> None:
        """Unsubscribes logger on close.
        """
        self._qt_log_subscriber.unsubscribe()
        super().closeEvent(event)
