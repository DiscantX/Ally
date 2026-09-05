"""Timing Waterfall dev dock panel rendering turn stage timings.
"""
from typing import Optional, Any
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem


class TimingPanel(QWidget):
    """Dock panel displaying turn execution stage timings from turn_traces.
    """
    def __init__(self, core: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__timingPanel")
        self._core = core

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._table = QTableWidget(self)
        self._table.setObjectName("devDock__timingTable")
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Turn", "Stage", "Duration (s)"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setProperty("themed", "devPanelTable")
        self._table.style().unpolish(self._table)
        self._table.style().polish(self._table)
        layout.addWidget(self._table)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll_timings)
        self._timer.start()

    def _poll_timings(self) -> None:
        """Polls turn_traces and populates timing table.
        """
        if self._core is None or not hasattr(self._core, "turn_traces"):
            return
        try:
            traces = list(self._core.turn_traces)
            rows = []
            for trace in traces:
                turn = getattr(trace, "turn", 0)
                timings = getattr(trace, "timings", {})
                for stage, duration in timings.items():
                    rows.append((turn, stage, duration))

            self._table.setRowCount(len(rows))
            for row, (turn, stage, duration) in enumerate(rows):
                self._table.setItem(row, 0, QTableWidgetItem(str(turn)))
                self._table.setItem(row, 1, QTableWidgetItem(str(stage)))
                self._table.setItem(row, 2, QTableWidgetItem(f"{duration:.4f}"))
        except Exception:
            pass

    def closeEvent(self, event: Any) -> None:
        """Stops poll timer on close.
        """
        self._timer.stop()
        super().closeEvent(event)
