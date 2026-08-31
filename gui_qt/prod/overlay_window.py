"""Prod Overlay Window shell assembling feed panel, input bar, and status strip with edge snapping and capture exclusion.
"""
from typing import Optional, Literal
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QScreen, QGuiApplication
from PySide6.QtWidgets import QWidget, QVBoxLayout
from gui_qt.prod.feed_panel import FeedPanel
from gui_qt.prod.input_bar import InputBar
from gui_qt.prod.status_strip import StatusStrip
from gui_qt.prod.settings_dialog import SettingsDialog
from interfaces.gui_qt.shell.capture_exclusion import exclude_hwnd_from_capture
from brain.state.shell_bounds_registry import SHELL_BOUNDS
from gui_qt.theming.theme import Theme, SIGNAL, SYNTHWAVE, build_stylesheet
from brain.state.entity_registry import EntityRegistry

TEMPLATE_PATH = "gui_qt/theming/base.qss.tmpl"


class ProdOverlayWindow(QWidget):
    """Frameless translucent top-level window for player-facing prod overlay companion shell.
    """

    def __init__(self, theme: Theme = SIGNAL, registry: Optional[EntityRegistry] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme = theme
        self._registry = registry
        self._snapped_edge: Optional[Literal["left", "right", "top", "bottom"]] = None
        self._snap_threshold = 28
        self._docked_width = 340
        self._expanded_max_width = 560
        self._is_dragging = False
        self._drag_position = QPoint()

        # Window flags & attributes
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("prodOverlayWindow")
        self.resize(380, 520)

        # Main layout container with styling applied via QSS
        self._container = QWidget(self)
        self._container.setObjectName("prodOverlayContainer")
        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(4)

        # Components
        self._status_strip = StatusStrip(self._theme, personality_name="Ally", parent=self._container)
        self._status_strip.settings_requested.connect(self._open_settings)
        self._status_strip.dev_window_requested.connect(self._on_dev_requested)
        container_layout.addWidget(self._status_strip)

        self._feed_panel = FeedPanel(self._theme, self._registry, parent=self._container)
        container_layout.addWidget(self._feed_panel, stretch=1)

        self._input_bar = InputBar(self._theme, parent=self._container)
        self._input_bar.message_sent.connect(self._on_message_sent)
        self._input_bar.expand_toggled.connect(self._on_expand_toggled)
        container_layout.addWidget(self._input_bar)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._container)

        self._apply_theme()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        exclude_hwnd_from_capture(int(self.winId()))
        self._update_shell_bounds()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._update_shell_bounds()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._container.setGeometry(self.rect())
        self._update_shell_bounds()

    def closeEvent(self, event) -> None:
        SHELL_BOUNDS.unregister("prod_overlay")
        super().closeEvent(event)

    def _update_shell_bounds(self) -> None:
        """Updates absolute screen bounds in SHELL_BOUNDS registry for self-capture exclusion.
        """
        pos = self.pos()
        size = self.size()
        SHELL_BOUNDS.update("prod_overlay", pos.x(), pos.y(), size.width(), size.height())

    def _apply_theme(self) -> None:
        """Applies stylesheet built from current theme.
        """
        qss = build_stylesheet(self._theme, TEMPLATE_PATH)
        # Add container background override for translucency support
        container_qss = f"""
            #prodOverlayContainer {{
                background-color: {self._theme.bg_base};
                border: 1px solid {self._theme.border};
                border-radius: 8px;
            }}
            {qss}
        """
        self.setStyleSheet(container_qss)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Allow dragging from status strip or top area
            self._is_dragging = True
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._is_dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            self._snapped_edge = None  # unsnap on free drag
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            self._check_edge_snap()
            event.accept()

    def _check_edge_snap(self) -> None:
        """Checks screen bounds and snaps window to edge if within threshold.
        """
        screen: QScreen = self.screen() or QGuiApplication.screenAt(self.pos())
        if not screen:
            return
        avail: QRect = screen.availableGeometry()
        geo = self.frameGeometry()

        # Distances to screen edges
        d_left = abs(geo.left() - avail.left())
        d_right = abs(avail.right() - geo.right())
        d_top = abs(geo.top() - avail.top())
        d_bottom = abs(avail.bottom() - geo.bottom())

        if d_left < self._snap_threshold:
            self.move(avail.left(), geo.top())
            self.resize(self._docked_width, geo.height())
            self._snapped_edge = "left"
        elif d_right < self._snap_threshold:
            self.move(avail.right() - geo.width(), geo.top())
            self.resize(self._docked_width, geo.height())
            self._snapped_edge = "right"
        elif d_top < self._snap_threshold:
            self.move(geo.left(), avail.top())
            self._snapped_edge = "top"
        elif d_bottom < self._snap_threshold:
            self.move(geo.left(), avail.bottom() - geo.height())
            self._snapped_edge = "bottom"

    def _on_expand_toggled(self, expanded: bool) -> None:
        """Expands or collapses window width for full chat mode.
        """
        geo = self.frameGeometry()
        if expanded:
            new_w = self._expanded_max_width
            if self._snapped_edge == "right":
                self.move(geo.right() - new_w, geo.top())
            self.resize(new_w, geo.height() + 150)
        else:
            new_w = self._docked_width
            if self._snapped_edge == "right":
                self.move(geo.right() - new_w, geo.top())
            self.resize(new_w, max(300, geo.height() - 150))

    def _on_message_sent(self, text: str, mode: str) -> None:
        """Handles sending message from input bar to feed and core.
        """
        self._feed_panel.add_message("player", "You", text, speaker_type="player")
        # Subclass / main wiring hooks into core send_message here

    def _open_settings(self) -> None:
        """Opens settings dialog.
        """
        dialog = SettingsDialog(self._theme.name, "Ally", self)
        dialog.settings_saved.connect(self._apply_new_settings)
        dialog.exec()

    def _apply_new_settings(self, theme_name: str, personality_name: str) -> None:
        """Applies newly selected theme and personality.
        """
        if theme_name == "Synthwave":
            self._theme = SYNTHWAVE
        else:
            self._theme = SIGNAL
        self._apply_theme()
        self._status_strip.set_personality(personality_name)

    def _on_dev_requested(self) -> None:
        """Emitted when dev window is requested. Handled by main application wiring.
        """
        pass

    def add_ally_message(self, personality_name: str, text: str) -> None:
        """Public method to add an incoming Ally message to the feed.
        """
        self._feed_panel.add_message(personality_name, personality_name, text, speaker_type="ally")
