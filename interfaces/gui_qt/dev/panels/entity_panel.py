"""Entity Registry polled QTableWidget dev dock panel.
"""
from typing import Optional, Any
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem
from interfaces.gui_qt.theming.theme import NEUTRAL_CONTENT_THEME


class EntityPanel(QWidget):
    """Dock panel polling EntityRegistry and displaying entities in a QTableWidget.
    """
    def __init__(self, core: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__entityPanel")
        self._core = core

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._table = QTableWidget(self)
        self._table.setObjectName("devDock__entityTable")
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["ID", "Name", "Type", "Facts Count"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setStyleSheet(f"background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; color: {NEUTRAL_CONTENT_THEME.fg_primary}; gridline-color: {NEUTRAL_CONTENT_THEME.border};")
        layout.addWidget(self._table)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll_entities)
        self._timer.start()

    def _poll_entities(self) -> None:
        """Polls EntityRegistry entities and populates table.
        """
        if self._core is None or getattr(self._core, "registry", None) is None:
            return
        registry = self._core.registry
        try:
            entities = list(registry._entities.values()) if hasattr(registry, "_entities") else []
            self._table.setRowCount(len(entities))
            for row, ent in enumerate(entities):
                ent_id = str(getattr(ent, "entity_id", ""))
                name = str(getattr(ent, "name", ""))
                ent_type = str(getattr(ent, "entity_type", getattr(ent, "type", "")))
                facts_count = len(getattr(ent, "facts", []))

                self._table.setItem(row, 0, QTableWidgetItem(ent_id))
                self._table.setItem(row, 1, QTableWidgetItem(name))
                self._table.setItem(row, 2, QTableWidgetItem(ent_type))
                self._table.setItem(row, 3, QTableWidgetItem(str(facts_count)))
        except Exception:
            pass

    def closeEvent(self, event: Any) -> None:
        """Stops poll timer on close.
        """
        self._timer.stop()
        super().closeEvent(event)
