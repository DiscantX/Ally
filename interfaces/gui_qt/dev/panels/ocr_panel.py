"""OCR and Screen Classification dev dock panel.
"""
from typing import Optional, Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QTableWidget, QTableWidgetItem, QGroupBox
from interfaces.gui_qt.theming.theme import Theme, SLATE


class OcrPanel(QWidget):
    """Dock panel showing screen classification, confidence, confirmed facts table, and skip reasons.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__ocrPanel")
        self._theme: Theme = SLATE
        self._last_payload: Optional[dict[str, Any]] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Header strip container
        header_group = QGroupBox("Screen Classification & Metadata", self)
        header_group.setProperty("themed", "devPanelCard")
        header_layout = QGridLayout(header_group)

        # Labels for Screen Name, Confidence, Is Draft, Category, Skip Reason
        self._screen_name_title = QLabel("Screen Name:", header_group)
        self._screen_name_title.setProperty("themed", "devPanelTitle")
        self._screen_name_val = QLabel("unknown", header_group)

        self._confidence_title = QLabel("Confidence:", header_group)
        self._confidence_title.setProperty("themed", "devPanelTitle")
        self._confidence_val = QLabel("0.00", header_group)

        self._is_draft_title = QLabel("Is Draft Match:", header_group)
        self._is_draft_title.setProperty("themed", "devPanelTitle")
        self._is_draft_val = QLabel("No", header_group)

        self._category_title = QLabel("Screen Category:", header_group)
        self._category_title.setProperty("themed", "devPanelTitle")
        self._category_val = QLabel("None", header_group)

        self._skip_reason_title = QLabel("Skip Reason:", header_group)
        self._skip_reason_title.setProperty("themed", "devPanelTitle")
        self._skip_reason_val = QLabel("none", header_group)

        header_layout.addWidget(self._screen_name_title, 0, 0)
        header_layout.addWidget(self._screen_name_val, 0, 1)
        header_layout.addWidget(self._confidence_title, 0, 2)
        header_layout.addWidget(self._confidence_val, 0, 3)

        header_layout.addWidget(self._is_draft_title, 1, 0)
        header_layout.addWidget(self._is_draft_val, 1, 1)
        header_layout.addWidget(self._category_title, 1, 2)
        header_layout.addWidget(self._category_val, 1, 3)

        header_layout.addWidget(self._skip_reason_title, 2, 0)
        header_layout.addWidget(self._skip_reason_val, 2, 1)

        layout.addWidget(header_group)

        # Table for ConfirmedFacts
        self._table = QTableWidget(self)
        self._table.setObjectName("devDock__ocrTable")
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Key", "Value", "Source"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSortingEnabled(True)
        self._table.setProperty("themed", "devPanelTable")
        self._table.style().unpolish(self._table)
        self._table.style().polish(self._table)
        layout.addWidget(self._table)

    def set_active_theme(self, theme: Theme) -> None:
        """Updates active theme and refreshes display if payload is cached.
        """
        self._theme = theme
        self._table.style().unpolish(self._table)
        self._table.style().polish(self._table)
        if self._last_payload is not None:
            self.handle_ocr_result(self._last_payload)

    def handle_ocr_result(self, payload: dict[str, Any]) -> None:
        """Formats and displays OCR / screen classification payload in header strip and table widget.
        """
        self._last_payload = payload
        if not isinstance(payload, dict):
            self._screen_name_val.setText(str(payload))
            self._confidence_val.setText("0.00")
            self._is_draft_val.setText("No")
            self._category_val.setText("None")
            self._skip_reason_val.setText("none")
            self._table.setRowCount(0)
            return

        screen_name = payload.get("screen_name", "unknown")
        confidence = payload.get("confidence", 0.0)
        is_draft = payload.get("is_draft", False)
        screen_category = payload.get("screen_category", "None")
        skip_reason = payload.get("skip_scribe_reason", "none")

        self._screen_name_val.setText(str(screen_name))
        self._confidence_val.setText(f"{confidence:.2f}")
        self._is_draft_val.setText("Yes" if is_draft else "No")
        self._category_val.setText(str(screen_category) if screen_category else "None")
        self._skip_reason_val.setText(str(skip_reason) if skip_reason else "none")

        facts = payload.get("confirmed_facts", [])
        self._table.setRowCount(len(facts))
        for row, fact in enumerate(facts):
            key = getattr(fact, "key", fact.get("key", "key") if isinstance(fact, dict) else "key")
            val = getattr(fact, "value", fact.get("value", "val") if isinstance(fact, dict) else "val")
            src = getattr(fact, "source", fact.get("source", "src") if isinstance(fact, dict) else "src")

            self._table.setItem(row, 0, QTableWidgetItem(str(key)))
            self._table.setItem(row, 1, QTableWidgetItem(str(val)))
            self._table.setItem(row, 2, QTableWidgetItem(str(src)))
