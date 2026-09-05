"""Memory summaries polled dev dock panel with embedded log tail.
"""
from typing import Optional, Any
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from interfaces.gui_qt.theming.theme import SLATE, SIGNAL, SYNTHWAVE
from theming.palettes import resolve_module_color
from infrastructure.logger.logger import LogEntry
from interfaces.gui_qt.dev.qt_safe_logger import QtSafeLogSubscriber


class MemoryPanel(QWidget):
    """Dock panel polling memory summaries and displaying memory log tail.
    """
    def __init__(self, core: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__memoryPanel")
        self._core = core
        self._log_entries: list[LogEntry] = []
        self._active_theme_name: str = "Slate"
        self._themes = {"Slate": SLATE, "Signal": SIGNAL, "Synthwave": SYNTHWAVE}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._summary_text = QTextEdit(self)
        self._summary_text.setObjectName("devDock__memorySummaryText")
        self._summary_text.setReadOnly(True)
        self._summary_text.setProperty("themed", "devPanelText")
        self._summary_text.style().unpolish(self._summary_text)
        self._summary_text.style().polish(self._summary_text)
        self._summary_text.setPlainText("Polling memory summaries...")
        layout.addWidget(self._summary_text, stretch=3)

        self._log_text = QTextEdit(self)
        self._log_text.setObjectName("devDock__memoryLogTail")
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(90)
        self._log_text.setProperty("themed", "devPanelText")
        self._log_text.style().unpolish(self._log_text)
        self._log_text.style().polish(self._log_text)
        layout.addWidget(self._log_text, stretch=1)

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._poll_memory)
        self._timer.start()

        self._qt_log_subscriber = QtSafeLogSubscriber(self._on_log_entry, self)

    def set_active_theme(self, theme: Theme) -> None:
        self._active_theme_name = theme.name
        self._refresh_log_tail()

    def _format_entry_html(self, entry: LogEntry) -> str:
        theme = self._themes.get(self._active_theme_name, SLATE)
        mod_color = resolve_module_color(self._active_theme_name, entry.brain_name)
        level_lower = entry.level.lower()
        level_color = theme.log_level_colors.get(level_lower, theme.fg_primary)
        return f'<span style="color: {mod_color};">[{entry.brain_name}]</span> <span style="color: {level_color};">{entry.message}</span>'

    def _refresh_log_tail(self) -> None:
        html_lines = [self._format_entry_html(e) for e in self._log_entries]
        self._log_text.setHtml("<br>".join(html_lines))

    def _poll_memory(self) -> None:
        """Polls memory manager summaries.
        """
        if self._core is None or getattr(self._core, "memory_manager", None) is None:
            self._summary_text.setPlainText("(Memory manager not initialized)")
            return
        mm = self._core.memory_manager
        try:
            parts = []
            if hasattr(mm, "get_cross_session_summary"):
                parts.append(f"--- Cross-Session ---\n{mm.get_cross_session_summary()}")
            if hasattr(mm, "get_long_term_summary"):
                parts.append(f"--- Long-Term ---\n{mm.get_long_term_summary()}")
            if hasattr(mm, "get_personality_digest"):
                parts.append(f"--- Personality Digest ---\n{mm.get_personality_digest()}")
            if hasattr(mm, "build_context"):
                parts.append(f"--- Context Summary ---\n{mm.build_context()}")
            self._summary_text.setPlainText("\n\n".join(parts) if parts else "(no memory records)")
        except Exception as e:
            self._summary_text.setPlainText(f"Error polling memory: {e}")

    def _on_log_entry(self, entry: LogEntry) -> None:
        """Receives log entries filtered for memory/save channels.
        """
        memory_brains = {"NarrativeMemory", "PersonalityMemory", "SaveTracker"}
        if entry.brain_name in memory_brains or "memory" in entry.method_name.lower():
            self._log_entries.append(entry)
            if len(self._log_entries) > 5:
                self._log_entries.pop(0)
            self._refresh_log_tail()

    def closeEvent(self, event: Any) -> None:
        """Stops timer and unsubscribes logger on close.
        """
        self._timer.stop()
        self._qt_log_subscriber.unsubscribe()
        super().closeEvent(event)
