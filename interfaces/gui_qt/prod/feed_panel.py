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
from interfaces.gui_qt.prod.message_formatting import format_message_html
from interfaces.gui_qt.theming.palette_hash import color_for_key
from interfaces.gui_qt.theming.theme import Theme


class FeedPanel(QWidget):
    """Scrollable feed of message rows with speaker dynamic properties, colored name labels,
    rich text body labels, and auto-scroll-to-bottom logic when at bottom.
    """

    def __init__(self, theme: Theme, registry: Optional[EntityRegistry] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme = theme
        self._registry = registry
        self._active_streaming_row: Optional[QWidget] = None
        self._active_streaming_body_label: Optional[QLabel] = None
        self._active_streaming_text: str = ""

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

        self._scroll_to_bottom()

    def begin_streaming_message(self, speaker_id: str, speaker_display_name: str, speaker_type: str = "ally") -> None:
        """Begins a new streaming message row.
        """
        self._active_streaming_row = QWidget()
        self._active_streaming_row.setObjectName("messageRow")
        self._active_streaming_row.setProperty("speaker", speaker_type)
        self._active_streaming_row.style().unpolish(self._active_streaming_row)
        self._active_streaming_row.style().polish(self._active_streaming_row)

        row_layout = QVBoxLayout(self._active_streaming_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(2)

        name_label = QLabel(speaker_display_name, self._active_streaming_row)
        name_label.setObjectName("messageRow__nameLabel")
        if speaker_type == "player":
            name_color = self._theme.fg_primary
        elif speaker_type == "system":
            name_color = self._theme.fg_muted
        else:
            name_color = color_for_key(speaker_id, self._theme.companion_palette)
        name_label.setStyleSheet(f"color: {name_color}; font-weight: bold; font-size: 12px;")
        row_layout.addWidget(name_label)

        self._active_streaming_body_label = QLabel(self._active_streaming_row)
        self._active_streaming_body_label.setObjectName("messageRow__bodyLabel")
        self._active_streaming_body_label.setTextFormat(Qt.TextFormat.RichText)
        self._active_streaming_body_label.setWordWrap(True)
        self._active_streaming_body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._active_streaming_body_label.setStyleSheet(f"color: {self._theme.fg_primary}; font-size: 13px;")
        row_layout.addWidget(self._active_streaming_body_label)

        self._active_streaming_text = ""
        count = self._container_layout.count()
        self._container_layout.insertWidget(count - 1, self._active_streaming_row)
        self._scroll_to_bottom()

    def append_streaming_chunk(self, chunk: str) -> None:
        """Appends a chunk to the active streaming message and scrolls down.
        """
        if not self._active_streaming_body_label:
            self.begin_streaming_message("Ally", "Ally", "ally")

        self._active_streaming_text += chunk
        formatted_html = format_message_html(self._active_streaming_text, self._registry, self._theme)
        self._active_streaming_body_label.setText(formatted_html)
        self._scroll_to_bottom()

    def finalize_streaming_message(self, final_text: Optional[str] = None) -> None:
        """Finalizes the streaming message.
        """
        if final_text is not None and self._active_streaming_body_label:
            self._active_streaming_text = final_text
            formatted_html = format_message_html(self._active_streaming_text, self._registry, self._theme)
            self._active_streaming_body_label.setText(formatted_html)
        self._active_streaming_row = None
        self._active_streaming_body_label = None
        self._active_streaming_text = ""
        self._scroll_to_bottom()

    def set_registry(self, registry: EntityRegistry) -> None:
        """Sets or updates the entity registry for rich text formatting.
        """
        self._registry = registry

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
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._scroll_bar.setValue(self._scroll_bar.maximum()))
