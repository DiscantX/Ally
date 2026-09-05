# Verified PySide6QtAds API: CDockManager, CDockWidget, DockWidgetArea, saveState, restoreState (v5.0.0.2)
"""Dev Inspector Window (QMainWindow) with Qt Advanced Docking System (ADS) dockable panels, CoreBridge integration, and QSettings layout persistence.
"""
from typing import Optional, Any
import os
import json
import base64
from pathlib import Path
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QWidget, QMessageBox, QFileDialog
import PySide6QtAds as QtAds
from brain.reasoning.core import AllyCore
from interfaces.gui_qt.dev.bridge import CoreBridge
from interfaces.gui_qt.dev.panels.vision_panel import VisionPanel
from interfaces.gui_qt.dev.panels.debug_panel import DebugPanel
from interfaces.gui_qt.dev.panels.ocr_panel import OcrPanel
from interfaces.gui_qt.dev.panels.scribe_panel import ScribePanel
from interfaces.gui_qt.dev.panels.ally_panel import AllyPanel
from interfaces.gui_qt.dev.panels.entity_panel import EntityPanel
from interfaces.gui_qt.dev.panels.memory_panel import MemoryPanel
from interfaces.gui_qt.dev.panels.timing_panel import TimingPanel
from interfaces.gui_qt.dev.panels.output_panel import OutputPanel
from interfaces.gui_qt.dev.panels.thinking_panel import ThinkingPanel
from interfaces.gui_qt.theming.theme import Theme, SLATE, SIGNAL, SYNTHWAVE, build_stylesheet, TEMPLATE_PATH
from interfaces.gui_qt.shell.capture_exclusion import exclude_hwnd_from_capture
from brain.state.shell_bounds_registry import SHELL_BOUNDS


class DevInspectorWindow(QMainWindow):
    """Dev inspector QMainWindow exposing all pipeline stages, memory, registry, and logs in ADS dock panels.
    """
    _instance: Optional["DevInspectorWindow"] = None

    @classmethod
    def get_instance(cls, core: Optional[AllyCore], theme: Theme, parent: Optional[QWidget] = None) -> "DevInspectorWindow":
        """Singleton manager: returns existing instance or creates a new one, raising and focusing it.
        """
        if cls._instance is None:
            cls._instance = DevInspectorWindow(core, theme, parent)
        else:
            if core is not None:
                cls._instance.set_core(core)
            # Do NOT override persisted active theme on subsequent get_instance calls
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()
        return cls._instance

    def __init__(self, core: Optional[AllyCore], theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devInspectorWindow")
        self.setWindowTitle("Ally Dev Inspector")
        self.resize(1400, 900)
        
        # 1. Resolve icon path reliably using absolute path
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))  # interfaces/gui_qt/dev
        project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
        icon_path = os.path.join(project_root, "assets", "ally_icon_32x32.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._core: Optional[AllyCore] = None
        self._bridge = CoreBridge(parent=self)
        self._signals_connected = False

        self._settings = QSettings("Ally", "DevInspectorWindow")
        persisted_theme_name = self._settings.value("devThemeName")
        if persisted_theme_name in ("Slate", "Signal", "Synthwave"):
            self._active_theme_name = persisted_theme_name
        else:
            self._active_theme_name = theme.name if theme and hasattr(theme, "name") and theme.name in ("Slate", "Signal", "Synthwave") else "Slate"
            self._settings.setValue("devThemeName", self._active_theme_name)

        self._theme = {"Slate": SLATE, "Signal": SIGNAL, "Synthwave": SYNTHWAVE}[self._active_theme_name]
        self._dev_font_scale = float(self._settings.value("devFontScale", 1.0))

        self.setStyleSheet(build_stylesheet(self._theme, TEMPLATE_PATH, dev_font_scale=self._dev_font_scale))

        # Setup ADS Dock Manager
        self._dock_manager = QtAds.CDockManager(self)

        # Setup Docks
        self._setup_docks()

        # Setup Menus
        self._setup_menus()

        if core is not None:
            self.set_core(core)

        self._apply_active_theme()

    def set_active_theme(self, theme: Any) -> None:
        """Sets the active theme by Theme object or name string, persists, rebuilds stylesheet, and updates panels.
        """
        if hasattr(theme, "name") and theme.name in ("Slate", "Signal", "Synthwave"):
            self._active_theme_name = theme.name
        elif isinstance(theme, str) and theme in ("Slate", "Signal", "Synthwave"):
            self._active_theme_name = theme
        self._apply_active_theme()

    def _apply_active_theme(self) -> None:
        """Resolves active theme from name, rebuilds stylesheet, updates menu checks, persists, and propagates to panels.
        """
        self._theme = {"Slate": SLATE, "Signal": SIGNAL, "Synthwave": SYNTHWAVE}[self._active_theme_name]
        self._rebuild_stylesheet()
        self._settings.setValue("devThemeName", self._active_theme_name)
        self._update_theme_menu_checks()

        for panel_attr in ["_scribe_panel", "_ally_panel", "_ocr_panel", "_vision_panel", "_debug_panel", "_entity_panel", "_timing_panel", "_memory_panel", "_output_panel", "_thinking_panel"]:
            if hasattr(self, panel_attr):
                panel = getattr(self, panel_attr)
                if hasattr(panel, "set_active_theme"):
                    panel.set_active_theme(self._theme)

    def _set_active_theme_name(self, name: str) -> None:
        if name in ("Slate", "Signal", "Synthwave"):
            self._active_theme_name = name
            self._apply_active_theme()

    def _update_theme_menu_checks(self) -> None:
        if hasattr(self, "_theme_actions"):
            for name, act in self._theme_actions.items():
                act.setChecked(name == self._active_theme_name)

    def set_core(self, core: AllyCore) -> None:
        self._core = core
        self._bridge.set_core(core)
        self._timing_panel._core = core
        self._entity_panel._core = core
        self._memory_panel._core = core
        self._vision_panel._core = core

        if not self._signals_connected:
            self._signals_connected = True
            # Connect CoreBridge signals
            self._bridge.pipeline_image_ready.connect(self._vision_panel.handle_pipeline_image)
            self._bridge.debug_overlay_ready.connect(self._debug_panel.handle_debug_overlay)
            self._bridge.ocr_result_ready.connect(self._ocr_panel.handle_ocr_result)
            self._bridge.scribe_output_ready.connect(self._scribe_panel.handle_scribe_output)
            self._bridge.ally_output_ready.connect(self._ally_panel.handle_ally_output)
            # Thinking panel signal connections
            self._bridge.thinking_stream_begin.connect(self._thinking_panel.handle_thinking_begin)
            self._bridge.thinking_stream_chunk.connect(self._thinking_panel.handle_thinking_chunk)
            self._bridge.thinking_stream_reset.connect(self._thinking_panel.handle_thinking_reset)
            self._bridge.thinking_stream_finalize.connect(self._thinking_panel.handle_thinking_finalize)

        # Restore dock layout state from QSettings via CDockManager
        self._settings = QSettings("Ally", "DevInspectorWindow")
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        ads_state = self._settings.value("adsState")
        if ads_state:
            self._dock_manager.restoreState(ads_state)
        else:
            # Check for shipped default layout in cabinet/configs/layouts/system/default_dev_layout.json
            default_path = os.path.join("cabinet", "configs", "layouts", "system", "default_dev_layout.json")
            if os.path.exists(default_path):
                try:
                    with open(default_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        b64_state = data.get("adsState")
                        if b64_state:
                            state_bytes = base64.b64decode(b64_state.encode("utf-8"))
                            self._dock_manager.restoreState(state_bytes)
                except Exception as e:
                    from infrastructure.logger import log
                    log("Failed to load shipped default layout: {e}", e=e, level="warning")

        # Ensure all dock widgets are visible
        for dock in self.findChildren(QtAds.CDockWidget):
            dock.setVisible(True)
            dock.show()

    def _setup_docks(self) -> None:
        """Creates and adds all dock panels to the CDockManager.
        """
        # 1. Vision Pipeline
        self._vision_panel = VisionPanel(self)
        vision_dock = QtAds.CDockWidget("Vision Pipeline")
        vision_dock.setObjectName("devDock__vision")
        vision_dock.setWidget(self._vision_panel)
        self._dock_manager.addDockWidget(QtAds.DockWidgetArea.LeftDockWidgetArea, vision_dock)

        # 2. Debug Overlay
        self._debug_panel = DebugPanel(self)
        debug_dock = QtAds.CDockWidget("Debug Overlay")
        debug_dock.setObjectName("devDock__debug")
        debug_dock.setWidget(self._debug_panel)
        self._dock_manager.addDockWidgetTab(QtAds.DockWidgetArea.LeftDockWidgetArea, debug_dock)

        # 3. OCR / Screen Classification
        self._ocr_panel = OcrPanel(self)
        self._ocr_panel.set_active_theme(self._theme)
        ocr_dock = QtAds.CDockWidget("OCR / Classification")
        ocr_dock.setObjectName("devDock__ocr")
        ocr_dock.setWidget(self._ocr_panel)
        self._dock_manager.addDockWidgetTab(QtAds.DockWidgetArea.LeftDockWidgetArea, ocr_dock)

        # 4. Scribe Output
        self._scribe_panel = ScribePanel(self)
        self._scribe_panel.set_active_theme(self._theme)
        scribe_dock = QtAds.CDockWidget("Scribe (JSON)")
        scribe_dock.setObjectName("devDock__scribe")
        scribe_dock.setWidget(self._scribe_panel)
        self._dock_manager.addDockWidget(QtAds.DockWidgetArea.RightDockWidgetArea, scribe_dock)

        # 5. Ally Output
        self._ally_panel = AllyPanel(self)
        self._ally_panel.set_active_theme(self._theme)
        ally_dock = QtAds.CDockWidget("Ally (JSON)")
        ally_dock.setObjectName("devDock__ally")
        ally_dock.setWidget(self._ally_panel)
        self._dock_manager.addDockWidgetTab(QtAds.DockWidgetArea.RightDockWidgetArea, ally_dock)

        # 6. Entity Registry
        self._entity_panel = EntityPanel(self._core, self)
        entity_dock = QtAds.CDockWidget("Entity Registry")
        entity_dock.setObjectName("devDock__entity")
        entity_dock.setWidget(self._entity_panel)
        self._dock_manager.addDockWidgetTab(QtAds.DockWidgetArea.RightDockWidgetArea, entity_dock)

        # 7. Memory
        self._memory_panel = MemoryPanel(self._core, self)
        memory_dock = QtAds.CDockWidget("Memory")
        memory_dock.setObjectName("devDock__memory")
        memory_dock.setWidget(self._memory_panel)
        self._dock_manager.addDockWidgetTab(QtAds.DockWidgetArea.RightDockWidgetArea, memory_dock)

        # 8. Timing Waterfall
        self._timing_panel = TimingPanel(self._core, self)
        timing_dock = QtAds.CDockWidget("Timing Waterfall")
        timing_dock.setObjectName("devDock__timing")
        timing_dock.setWidget(self._timing_panel)
        self._dock_manager.addDockWidget(QtAds.DockWidgetArea.BottomDockWidgetArea, timing_dock)

        # 9. Logs
        self._output_panel = OutputPanel(self)
        output_dock = QtAds.CDockWidget("Logs")
        output_dock.setObjectName("devDock__output")
        output_dock.setWidget(self._output_panel)
        self._dock_manager.addDockWidgetTab(QtAds.DockWidgetArea.BottomDockWidgetArea, output_dock)

        # 10. Thinking
        self._thinking_panel = ThinkingPanel(self)
        thinking_dock = QtAds.CDockWidget("Thinking")
        thinking_dock.setObjectName("devDock__thinking")
        thinking_dock.setWidget(self._thinking_panel)
        self._dock_manager.addDockWidgetTab(QtAds.DockWidgetArea.BottomDockWidgetArea, thinking_dock)

        # Set default active tabs
        vision_dock.raise_()
        scribe_dock.raise_()
        timing_dock.raise_()

        # Save default layout state for reset
        self._default_ads_state = self._dock_manager.saveState()

    def _setup_menus(self) -> None:
        """Sets up the menu bar with Theme menu, View menu, and Layout menu.
        """
        menu_bar = self.menuBar()

        # Theme menu
        theme_menu = menu_bar.addMenu("&Theme")
        from PySide6.QtGui import QActionGroup
        self._theme_actions = {}
        theme_action_group = QActionGroup(self)
        theme_action_group.setExclusive(True)

        for theme_name in ["Slate", "Signal", "Synthwave"]:
            act = theme_menu.addAction(theme_name)
            act.setCheckable(True)
            theme_action_group.addAction(act)
            self._theme_actions[theme_name] = act
            act.triggered.connect(lambda checked, name=theme_name: self._set_active_theme_name(name))

        self._update_theme_menu_checks()

        view_menu = menu_bar.addMenu("&View")

        for dock in self.findChildren(QtAds.CDockWidget):
            action = dock.toggleViewAction()
            view_menu.addAction(action)

        view_menu.addSeparator()

        # Text Size submenu
        text_size_menu = view_menu.addMenu("Text Size")
        from PySide6.QtGui import QActionGroup
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QSpinBox, QPushButton, QLabel

        self._font_scale_actions = {}
        action_group = QActionGroup(self)
        action_group.setExclusive(True)

        presets = [
            ("Smallest (0.75x)", 0.75),
            ("Small (0.85x)", 0.85),
            ("Medium (1.0x)", 1.0),
            ("Large (1.2x)", 1.2),
            ("Largest (1.4x)", 1.4),
        ]

        for label, scale in presets:
            act = text_size_menu.addAction(label)
            act.setCheckable(True)
            action_group.addAction(act)
            self._font_scale_actions[scale] = act
            act.triggered.connect(lambda checked, s=scale: self._set_font_scale(s))

        text_size_menu.addSeparator()
        custom_act = text_size_menu.addAction("Custom...")
        custom_act.triggered.connect(self._open_custom_font_size_dialog)

        self._update_font_scale_menu_checks()

        view_menu.addSeparator()
        reset_action = view_menu.addAction("Reset Layout")
        reset_action.triggered.connect(self._reset_layout)

        # Dedicated Layout menu
        layout_menu = menu_bar.addMenu("&Layout")
        
        save_layout_action = layout_menu.addAction("Save Layout As...")
        save_layout_action.triggered.connect(self._save_layout_dialog)

        load_layout_action = layout_menu.addAction("Load Layout...")
        load_layout_action.triggered.connect(self._load_layout_dialog)

        layout_menu.addSeparator()
        
        export_default_action = layout_menu.addAction("Export as Default Layout")
        export_default_action.triggered.connect(self._export_default_layout)

    def _save_layout_dialog(self) -> None:
        """Opens file dialog to save current window layout state to cabinet/configs/layouts/user/.
        """
        user_dir = os.path.join("cabinet", "configs", "layouts", "user")
        os.makedirs(user_dir, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Layout", user_dir, "Layout Files (*.json)"
        )
        if path:
            try:
                state_bytes = self._dock_manager.saveState()
                b64_state = base64.b64encode(state_bytes).decode("utf-8")
                payload = {"adsState": b64_state}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                QMessageBox.information(self, "Layout Saved", f"Layout successfully saved to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save layout: {e}")

    def _load_layout_dialog(self) -> None:
        """Opens file dialog to load a custom window layout state from cabinet/configs/layouts/.
        """
        layouts_dir = os.path.join("cabinet", "configs", "layouts")
        os.makedirs(layouts_dir, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Layout", layouts_dir, "Layout Files (*.json)"
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    b64_state = data.get("adsState")
                    if b64_state:
                        state_bytes = base64.b64decode(b64_state.encode("utf-8"))
                        self._dock_manager.restoreState(state_bytes)
                        self._settings = QSettings("Ally", "DevInspectorWindow")
                        self._settings.setValue("adsState", state_bytes)
                QMessageBox.information(self, "Layout Loaded", f"Layout successfully loaded from:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load layout: {e}")

    def _export_default_layout(self) -> None:
        """Exports current layout as the shippable system default layout under cabinet/configs/layouts/system/default_dev_layout.json.
        """
        system_dir = os.path.join("cabinet", "configs", "layouts", "system")
        os.makedirs(system_dir, exist_ok=True)
        path = os.path.join(system_dir, "default_dev_layout.json")
        try:
            state_bytes = self._dock_manager.saveState()
            b64_state = base64.b64encode(state_bytes).decode("utf-8")
            payload = {"adsState": b64_state}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            QMessageBox.information(self, "Default Layout Exported", f"Shippable default layout exported to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export default layout: {e}")

    def _reset_layout(self) -> None:
        """Resets the dock layout to the shipped default or in-memory default state and clears persisted state.
        """
        default_path = os.path.join("cabinet", "configs", "layouts", "system", "default_dev_layout.json")
        restored = False
        if os.path.exists(default_path):
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    b64_state = data.get("adsState")
                    if b64_state:
                        state_bytes = base64.b64decode(b64_state.encode("utf-8"))
                        self._dock_manager.restoreState(state_bytes)
                        restored = True
            except Exception:
                pass
        
        if not restored and hasattr(self, "_default_ads_state") and self._default_ads_state:
            self._dock_manager.restoreState(self._default_ads_state)

        self._settings = QSettings("Ally", "DevInspectorWindow")
        self._settings.remove("adsState")

    def _set_font_scale(self, scale: float) -> None:
        """Sets the font scale multiplier, persists it, and updates stylesheet.
        """
        self._dev_font_scale = scale
        self._settings.setValue("devFontScale", scale)
        self._update_font_scale_menu_checks()
        self._rebuild_stylesheet()

    def _update_font_scale_menu_checks(self) -> None:
        """Updates checked state of font scale preset menu items based on current scale.
        """
        for scale, act in self._font_scale_actions.items():
            if abs(self._dev_font_scale - scale) < 0.02:
                act.setChecked(True)
                break

    def _open_custom_font_size_dialog(self) -> None:
        """Opens custom point size dialog with QSpinBox (6-24 pt).
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("Custom Text Size")
        dialog.resize(300, 120)
        layout = QVBoxLayout(dialog)

        label = QLabel("Enter font point size (6 - 24 pt):", dialog)
        layout.addWidget(label)

        spin = QSpinBox(dialog)
        spin.setRange(6, 24)
        current_pt = int(round(self._dev_font_scale * 11.0))
        spin.setValue(max(6, min(24, current_pt)))
        layout.addWidget(spin)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK", dialog)
        cancel_btn = QPushButton("Cancel", dialog)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.Accepted:
            pt = spin.value()
            scale = pt / 11.0
            self._set_font_scale(scale)

    def _rebuild_stylesheet(self) -> None:
        """Rebuilds and applies stylesheet using active theme and font scale.
        """
        self.setStyleSheet(build_stylesheet(self._theme, TEMPLATE_PATH, dev_font_scale=self._dev_font_scale))

    def showEvent(self, event: Any) -> None:
        """Handles show event: registers display affinity and shell bounds.
        """
        super().showEvent(event)
        exclude_hwnd_from_capture(int(self.winId()))
        self._update_shell_bounds()

    def moveEvent(self, event: Any) -> None:
        """Handles move event: updates shell bounds.
        """
        super().moveEvent(event)
        self._update_shell_bounds()

    def resizeEvent(self, event: Any) -> None:
        """Handles resize event: updates shell bounds.
        """
        super().resizeEvent(event)
        self._update_shell_bounds()

    def closeEvent(self, event: Any) -> None:
        """Handles close event: saves state, unregisters shell bounds, and hides window instead of destroying.
        """
        if hasattr(self, "_settings"):
            self._settings.setValue("geometry", self.saveGeometry())
            self._settings.setValue("adsState", self._dock_manager.saveState())
        SHELL_BOUNDS.unregister("dev_inspector")
        event.ignore()
        self.hide()

    def _update_shell_bounds(self) -> None:
        """Updates absolute screen bounds in SHELL_BOUNDS registry.
        """
        pos = self.pos()
        size = self.size()
        SHELL_BOUNDS.update("dev_inspector", pos.x(), pos.y(), size.width(), size.height())
