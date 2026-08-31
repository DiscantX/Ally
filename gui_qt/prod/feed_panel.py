"""Scrollable feed panel for messages with speaker properties and auto-scroll.
"""
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QLabel,
    QSizePolicy,
)
from brain.state.entity_registry import EntityRegistry
from gui_qt.prod.message_formatting import format_message_html
from gui_qt.theming.palette_hash import color_for_key
from gui_qt.theming.theme import Theme


class FeedPanel(QWidget):
    """Scrollable feed of message rows with speaker dynamic properties, colored name labels,
    rich text body labels, and auto-scroll-to-bottom logic when at bottom.
    """

    def __init__(self, theme: Theme, registry: Optional[EntityRegistry] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme = theme
        self._registry = registry

        self.setObjectName("feedPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setObjectName("feedPanel__scrollArea")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container.setObjectName("feedPanel__container")
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(8, 8, 8, 8)
        self._container_layout.setSpacing(12)
        self._container_layout.addStretch(1)

        self._scroll_area.setWidget(self._container)
        layout.addWidget(self._scroll_area)

        # Track manual scroll vs auto-scroll
        self._scroll_bar = self._scroll_area.verticalScrollBar()

    def add_message(self, speaker_id: str, speaker_display_name: str, text: str, speaker_type: str = "ally") -> None:
        """Adds a message row to the feed. speaker_type can be 'ally', 'player', or 'system'.
        """
        is_at_bottom = self._is_scrolled_to_bottom()

        row_widget = QWidget()
        row_widget.setObjectName("messageRow")
        row_widget.setProperty("speaker", speaker_type)
        row_widget.style().unpolish(row_widget)
        row_widget.style().polish(row_widget)

        row_layout = QVBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(2)

        name_label = QLabel(speaker_display_name, row_widget)
        name_label.setObjectName("messageRow__nameLabel")
        if speaker_type == "player":
            name_color = self._theme.fg_primary
        elif speaker_type == "system":
            name_color = self._theme.fg_muted
        else:
            name_color = color_for_key(speaker_id, self._theme.companion_palette)
        name_label.setStyleSheet(f"color: {name_color}; font-weight: bold; font-size: 12px;")
        row_layout.addWidget(name_label)

        body_label = QLabel(row_widget)
        body_label.setObjectName("messageRow__bodyLabel")
        body_label.setTextFormat(Qt.TextFormat.RichText)
        body_label.setWordWrap(True)
        body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

        formatted_html = format_message_html(text, self._registry, self._theme)
        body_label.setText(formatted_html)
        body_label.setStyleSheet(f"color: {self._theme.fg_primary}; font-size: 13px;")
        row_layout.addWidget(body_label)

        # Insert before stretch
        count = self._container_layout.count()
        self._container_layout.insertWidget(count - 1, row_widget)

        if is_at_bottom:
            self._scroll_to_bottom()

    def clear_messages(self) -> None:
        """Clears all messages from the feed.
        """
        while self._container_layout.count() > 1:
            item = self._container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _is_scrolled_to_bottom(self) -> bool:
        """Checks if the scrollbar is currently at the bottom (within a small tolerance).
        """
        max_val = self._scroll_bar.maximum()
        curr_val = self._scroll_bar.value()
        return (max_val - curr_val) <= 20

    def _scroll_to_bottom(self) -> None:
        """Scrolls the scroll area to the maximum bottom position.
        """
        self._scroll_bar.setValue(self._scroll_bar.maximum())
