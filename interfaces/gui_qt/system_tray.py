from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from PySide6.QtGui import QIcon, QAction, QPixmap
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from infrastructure.logger import log


class SystemTrayManager:
    """Manages the system tray icon, context menu, and window toggle interactions for Ally."""

    def __init__(self, overlay: Any, shutdown_callback: Any) -> None:
        self._overlay = overlay
        self._shutdown_callback = shutdown_callback

        # 1. Resolve icon path
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))  # interfaces/gui_qt
        project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
        png_path = os.path.join(project_root, "assets", "ally_icon_32x32.png")
        
        log("Is system tray available: {avail}, icon path: {path}, exists: {ex}", avail=QSystemTrayIcon.isSystemTrayAvailable(), path=png_path, ex=os.path.exists(png_path), level="info")

        icon_loaded = False
        if os.path.exists(png_path):
            pixmap = QPixmap(png_path)
            if not pixmap.isNull():
                self._icon = QIcon(pixmap)
                icon_loaded = True
                log("Successfully loaded system tray icon from {path}", path=png_path, level="info")

        if not icon_loaded:
            log("CRITICAL ERROR: SystemTrayManager could not find/load icon at: {path}", path=png_path, level="error")
            app_inst = QApplication.instance()
            app_style = app_inst.style() if isinstance(app_inst, QApplication) else None
            if app_style:
                self._icon = app_style.standardIcon(app_style.StandardPixmap.SP_ComputerIcon)
            else:
                self._icon = QIcon()

        self._tray_icon = QSystemTrayIcon(self._icon)
        self._tray_icon.setToolTip("Ally — Gaming Companion")

        # 2. Build context menu
        self._menu = QMenu()
        
        self._toggle_action = QAction("Hide Overlay", self._menu)
        self._toggle_action.triggered.connect(self.toggle_overlay)
        self._menu.addAction(self._toggle_action)

        self._dev_action = QAction("Open Dev Window", self._menu)
        self._dev_action.triggered.connect(self.open_dev_window)
        self._menu.addAction(self._dev_action)

        self._menu.addSeparator()

        self._exit_action = QAction("Exit Ally", self._menu)
        self._exit_action.triggered.connect(self._shutdown_callback)
        self._menu.addAction(self._exit_action)

        self._tray_icon.setContextMenu(self._menu)

        # 3. Handle tray icon clicks
        self._tray_icon.activated.connect(self._on_tray_activated)

        self._tray_icon.show()
        log("SystemTrayManager initialized and shown in system tray.", level="info")

    def toggle_overlay(self) -> None:
        if self._overlay.isVisible():
            self._overlay.hide()
            self._toggle_action.setText("Show Overlay")
        else:
            self._overlay.show()
            self._overlay.raise_()
            self._toggle_action.setText("Hide Overlay")

    def open_dev_window(self) -> None:
        try:
            from interfaces.gui_qt.dev.dev_window import DevInspectorWindow
            from interfaces.gui_qt.theming.theme import SIGNAL
            # Use core if available or None, theme from overlay
            core = getattr(self._overlay, "_core", None) or getattr(self._overlay, "core", None)
            theme = getattr(self._overlay, "_theme", None) or SIGNAL
            dev_win = DevInspectorWindow.get_instance(core, theme)
            dev_win.show()
            dev_win.raise_()
        except Exception as e:
            log("Error opening Dev Inspector Window from tray: {e}", e=e, level="error")

    def update_overlay_visibility_state(self, visible: bool) -> None:
        if visible:
            self._toggle_action.setText("Hide Overlay")
        else:
            self._toggle_action.setText("Show Overlay")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Trigger on Trigger (single left click) or DoubleClick
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_overlay()

    def hide(self) -> None:
        """Hides and cleans up the system tray icon immediately upon application shutdown."""
        try:
            if hasattr(self, "_tray_icon") and self._tray_icon is not None:
                self._tray_icon.hide()
                self._tray_icon.setParent(None)
                log("System tray icon hidden and cleaned up.", level="info")
        except Exception as e:
            log("Error hiding system tray icon: {e}", e=e, level="warning")
