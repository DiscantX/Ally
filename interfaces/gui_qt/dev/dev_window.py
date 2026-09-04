# Verified PySide6QtAds API: CDockManager, CDockWidget, DockWidgetArea, saveState, restoreState (v5.0.0.2)
"""Dev Inspector Window (QMainWindow) with Qt Advanced Docking System (ADS) dockable panels, CoreBridge integration, and QSettings layout persistence.
"""
from typing import Optional, Any
import os
import json
import base64
from PySide6.QtCore import Qt, QSettings
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
from interfaces.gui_qt.theming.theme import Theme, build_stylesheet, TEMPLATE_PATH
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
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()
        return cls._instance

    def __init__(self, core: Optional[AllyCore], theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devInspectorWindow")
        self.setWindowTitle("Ally Dev Inspector")
        self.resize(1400, 900)

        self._core: Optional[AllyCore] = None
        self._theme = theme
        self._bridge = CoreBridge(parent=self)
        self._signals_connected = False

        self.setStyleSheet(build_stylesheet(theme, TEMPLATE_PATH))

        # Setup ADS Dock Manager
        self._dock_manager = QtAds.CDockManager(self)

        # Setup Docks
        self._setup_docks()

        # Setup Menus
        self._setup_menus()

        if core is not None:
            self.set_core(core)

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
        ocr_dock = QtAds.CDockWidget("OCR / Classification")
        ocr_dock.setObjectName("devDock__ocr")
        ocr_dock.setWidget(self._ocr_panel)
        self._dock_manager.addDockWidgetTab(QtAds.DockWidgetArea.LeftDockWidgetArea, ocr_dock)

        # 4. Scribe Output
        self._scribe_panel = ScribePanel(self)
        scribe_dock = QtAds.CDockWidget("Scribe (JSON)")
        scribe_dock.setObjectName("devDock__scribe")
        scribe_dock.setWidget(self._scribe_panel)
        self._dock_manager.addDockWidget(QtAds.DockWidgetArea.RightDockWidgetArea, scribe_dock)

        # 5. Ally Output
        self._ally_panel = AllyPanel(self)
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
        """Sets up the menu bar with View menu toggle actions for all dock widgets and Layout menu for save/load/reset.
        """
        menu_bar = self.menuBar()
        view_menu = menu_bar.addMenu("&View")

        for dock in self.findChildren(QtAds.CDockWidget):
            action = dock.toggleViewAction()
            view_menu.addAction(action)

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
        """Handles close event: saves state and unregisters shell bounds, resetting singleton.
        """
        if hasattr(self, "_settings"):
            self._settings.setValue("geometry", self.saveGeometry())
            self._settings.setValue("adsState", self._dock_manager.saveState())
        SHELL_BOUNDS.unregister("dev_inspector")
        DevInspectorWindow._instance = None
        super().closeEvent(event)

    def _update_shell_bounds(self) -> None:
        """Updates absolute screen bounds in SHELL_BOUNDS registry.
        """
        pos = self.pos()
        size = self.size()
        SHELL_BOUNDS.update("dev_inspector", pos.x(), pos.y(), size.width(), size.height())
