"""Memory summaries polled dev dock panel with embedded log tail.
"""
from typing import Optional, Any
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from gui_qt.theming.theme import NEUTRAL_CONTENT_THEME
from infrastructure.logger.logger import subscribe, unsubscribe, LogEntry


class MemoryPanel(QWidget):
    """Dock panel polling memory summaries and displaying memory log tail.
    """
    def __init__(self, core: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__memoryPanel")
        self._core = core
        self._log_tail: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._summary_text = QTextEdit(self)
        self._summary_text.setObjectName("devDock__memorySummaryText")
        self._summary_text.setReadOnly(True)
        self._summary_text.setStyleSheet(f"background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; color: {NEUTRAL_CONTENT_THEME.fg_primary}; font-family: monospace; font-size: 11px;")
        self._summary_text.setPlainText("Polling memory summaries...")
        layout.addWidget(self._summary_text, stretch=3)

        self._log_text = QTextEdit(self)
        self._log_text.setObjectName("devDock__memoryLogTail")
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(90)
        self._log_text.setStyleSheet(f"background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; color: {NEUTRAL_CONTENT_THEME.fg_primary}; font-family: monospace; font-size: 10px;")
        layout.addWidget(self._log_text, stretch=1)

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._poll_memory)
        self._timer.start()

        subscribe(self._on_log_entry)

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
            line = f"[{entry.brain_name}] {entry.message}"
            self._log_tail.append(line)
            if len(self._log_tail) > 5:
                self._log_tail.pop(0)
            self._log_text.setPlainText("\n".join(self._log_tail))

    def closeEvent(self, event: Any) -> None:
        """Stops timer and unsubscribes logger on close.
        """
        self._timer.stop()
        unsubscribe(self._on_log_entry)
        super().closeEvent(event)
