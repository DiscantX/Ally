"""Status strip component with connection indicator, personality badge, thinking animation, settings gear, and dev window trigger.
"""
from typing import Optional
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QFrame,
)
from gui_qt.theming.palette_hash import color_for_key
from gui_qt.theming.theme import Theme


class StatusStrip(QWidget):
    """Status strip widget showing connection, personality badge, thinking indicator, settings, and dev window trigger.
    """
    settings_requested = Signal()
    dev_window_requested = Signal()
    exit_requested = Signal()

    def __init__(self, theme: Theme, personality_name: str = "Ally", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme = theme
        self._personality_name = personality_name
        self._is_thinking = False
        self._thinking_dot_state = 0

        self.setObjectName("statusStrip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(8)

        # Connection dot
        self._conn_dot = QFrame(self)
        self._conn_dot.setObjectName("statusStrip__connectionDot")
        self._conn_dot.setFixedSize(10, 10)
        self._set_connection_status(True)
        layout.addWidget(self._conn_dot)

        # Personality badge with color swatch
        self._badge_container = QWidget(self)
        self._badge_container.setObjectName("statusStrip__personalityBadge")
        badge_layout = QHBoxLayout(self._badge_container)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setSpacing(4)

        self._swatch = QFrame(self._badge_container)
        self._swatch.setObjectName("statusStrip__swatch")
        self._swatch.setFixedSize(8, 8)
        swatch_color = color_for_key(self._personality_name, self._theme.companion_palette)
        self._swatch.setStyleSheet(f"background-color: {swatch_color}; border-radius: 4px;")
        badge_layout.addWidget(self._swatch)

        self._badge_label = QLabel(self._personality_name, self._badge_container)
        self._badge_label.setStyleSheet(f"color: {self._theme.fg_primary}; font-size: 11px; font-weight: bold;")
        badge_layout.addWidget(self._badge_label)
        layout.addWidget(self._badge_container)

        layout.addStretch(1)

        # Thinking indicator
        self._thinking_indicator = QLabel("", self)
        self._thinking_indicator.setObjectName("statusStrip__thinkingIndicator")
        self._thinking_indicator.setStyleSheet(f"color: {self._theme.accent_primary}; font-size: 11px;")
        self._thinking_indicator.setVisible(False)
        layout.addWidget(self._thinking_indicator)

        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(400)
        self._thinking_timer.timeout.connect(self._update_thinking_animation)

        # Settings gear button
        self._settings_btn = QToolButton(self)
        self._settings_btn.setObjectName("statusStrip__settingsButton")
        self._settings_btn.setText("⚙")
        self._settings_btn.setToolTip("Settings")
        self._settings_btn.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self._settings_btn)

        # Dev window button
        self._dev_btn = QToolButton(self)
        self._dev_btn.setObjectName("statusStrip__devButton")
        self._dev_btn.setText("🛠")
        self._dev_btn.setToolTip("Open Dev Inspector")
        self._dev_btn.clicked.connect(self.dev_window_requested.emit)
        layout.addWidget(self._dev_btn)

        # Exit / Close button
        self._exit_btn = QToolButton(self)
        self._exit_btn.setObjectName("statusStrip__exitButton")
        self._exit_btn.setText("✕")
        self._exit_btn.setToolTip("Close Ally")
        self._exit_btn.clicked.connect(self.exit_requested.emit)
        layout.addWidget(self._exit_btn)

    def set_personality(self, name: str) -> None:
        """Updates the personality badge name and swatch color.
        """
        self._personality_name = name
        self._badge_label.setText(name)
        swatch_color = color_for_key(name, self._theme.companion_palette)
        self._swatch.setStyleSheet(f"background-color: {swatch_color}; border-radius: 4px;")

    def set_thinking(self, thinking: bool) -> None:
        """Starts or stops the thinking indicator animation.
        """
        self._is_thinking = thinking
        if thinking:
            self._thinking_dot_state = 0
            self._thinking_indicator.setVisible(True)
            self._thinking_timer.start()
        else:
            self._thinking_timer.stop()
            self._thinking_indicator.setVisible(False)

    def _update_thinking_animation(self) -> None:
        """Updates pulsing dot animation text.
        """
        self._thinking_dot_state = (self._thinking_dot_state + 1) % 4
        dots = "." * self._thinking_dot_state
        self._thinking_indicator.setText(f"thinking{dots}")

    def _set_connection_status(self, connected: bool) -> None:
        """Updates connection indicator dot color.
        """
        color = self._theme.success if connected else self._theme.error
        self._conn_dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")

    def update_connection(self, status_str: str) -> None:
        """Handles connection status updates from core event hook.
        """
        connected = "connect" in status_str.lower() or "ok" in status_str.lower() or "true" in status_str.lower()
        self._set_connection_status(connected)
