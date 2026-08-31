"""Dev Inspector Window (QMainWindow) with dockable panels, CoreBridge integration, and QSettings layout persistence.
"""
from typing import Optional, Any
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QMainWindow, QDockWidget, QWidget, QMessageBox
from brain.reasoning.core import AllyCore
from gui_qt.dev.bridge import CoreBridge
from gui_qt.dev.panels.vision_panel import VisionPanel
from gui_qt.dev.panels.debug_panel import DebugPanel
from gui_qt.dev.panels.ocr_panel import OcrPanel
from gui_qt.dev.panels.scribe_panel import ScribePanel
from gui_qt.dev.panels.ally_panel import AllyPanel
from gui_qt.dev.panels.entity_panel import EntityPanel
from gui_qt.dev.panels.memory_panel import MemoryPanel
from gui_qt.dev.panels.timing_panel import TimingPanel
from gui_qt.dev.panels.output_panel import OutputPanel
from gui_qt.dev.panels.thinking_panel import ThinkingPanel
from gui_qt.theming.theme import Theme, build_stylesheet, TEMPLATE_PATH
from interfaces.gui_qt.shell.capture_exclusion import exclude_hwnd_from_capture
from brain.state.shell_bounds_registry import SHELL_BOUNDS


class DevInspectorWindow(QMainWindow):
    """Dev inspector QMainWindow exposing all pipeline stages, memory, registry, and logs in dock panels.
    """
    _instance: Optional["DevInspectorWindow"] = None

    @classmethod
    def get_instance(cls, core: AllyCore, theme: Theme, parent: Optional[QWidget] = None) -> "DevInspectorWindow":
        """Singleton manager: returns existing instance or creates a new one, raising and focusing it.
        """
        if cls._instance is None:
            cls._instance = DevInspectorWindow(core, theme, parent)
        else:
            cls._instance.show()
            cls._instance.raise_()
            cls._instance.activateWindow()
        return cls._instance

    def __init__(self, core: AllyCore, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devInspectorWindow")
        self.setWindowTitle("Ally Dev Inspector")
        self.resize(1400, 900)

        self._core = core
        self._theme = theme
        self._bridge = CoreBridge(core, self)

        self.setStyleSheet(build_stylesheet(theme, TEMPLATE_PATH))

        # Setup Docks
        self._setup_docks()

        # Connect CoreBridge signals
        self._bridge.pipeline_image_ready.connect(self._vision_panel.handle_pipeline_image)
        self._bridge.debug_overlay_ready.connect(self._debug_panel.handle_debug_overlay)
        self._bridge.ocr_result_ready.connect(self._ocr_panel.handle_ocr_result)
        self._bridge.scribe_output_ready.connect(self._scribe_panel.handle_scribe_output)
        self._bridge.ally_output_ready.connect(self._ally_panel.handle_ally_output)

        # Restore dock layout state from QSettings
        self._settings = QSettings("Ally", "DevInspectorWindow")
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = self._settings.value("windowState")
        if state:
            self.restoreState(state)

    def _setup_docks(self) -> None:
        """Creates and adds all dock panels to the QMainWindow.
        """
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowNestedDocks)

        # 1. Vision Pipeline
        self._vision_panel = VisionPanel(self)
        vision_dock = QDockWidget("Vision Pipeline", self)
        vision_dock.setObjectName("devDock__vision")
        vision_dock.setWidget(self._vision_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, vision_dock)

        # 2. Debug Overlay
        self._debug_panel = DebugPanel(self)
        debug_dock = QDockWidget("Debug Overlay", self)
        debug_dock.setObjectName("devDock__debug")
        debug_dock.setWidget(self._debug_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, debug_dock)
        self.tabifyDockWidget(vision_dock, debug_dock)

        # 3. OCR / Screen Classification
        self._ocr_panel = OcrPanel(self)
        ocr_dock = QDockWidget("OCR / Classification", self)
        ocr_dock.setObjectName("devDock__ocr")
        ocr_dock.setWidget(self._ocr_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, ocr_dock)
        self.tabifyDockWidget(vision_dock, ocr_dock)

        # 4. Scribe Output
        self._scribe_panel = ScribePanel(self)
        scribe_dock = QDockWidget("Scribe (JSON)", self)
        scribe_dock.setObjectName("devDock__scribe")
        scribe_dock.setWidget(self._scribe_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, scribe_dock)

        # 5. Ally Output
        self._ally_panel = AllyPanel(self)
        ally_dock = QDockWidget("Ally (JSON)", self)
        ally_dock.setObjectName("devDock__ally")
        ally_dock.setWidget(self._ally_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, ally_dock)
        self.tabifyDockWidget(scribe_dock, ally_dock)

        # 6. Entity Registry
        self._entity_panel = EntityPanel(self._core, self)
        entity_dock = QDockWidget("Entity Registry", self)
        entity_dock.setObjectName("devDock__entity")
        entity_dock.setWidget(self._entity_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, entity_dock)
        self.tabifyDockWidget(scribe_dock, entity_dock)

        # 7. Memory
        self._memory_panel = MemoryPanel(self._core, self)
        memory_dock = QDockWidget("Memory", self)
        memory_dock.setObjectName("devDock__memory")
        memory_dock.setWidget(self._memory_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, memory_dock)
        self.tabifyDockWidget(scribe_dock, memory_dock)

        # 8. Timing Waterfall
        self._timing_panel = TimingPanel(self._core, self)
        timing_dock = QDockWidget("Timing Waterfall", self)
        timing_dock.setObjectName("devDock__timing")
        timing_dock.setWidget(self._timing_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, timing_dock)

        # 9. Output / Logs
        self._output_panel = OutputPanel(self)
        output_dock = QDockWidget("Output / Logs", self)
        output_dock.setObjectName("devDock__output")
        output_dock.setWidget(self._output_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, output_dock)
        self.tabifyDockWidget(timing_dock, output_dock)

        # 10. Thinking (Stub)
        self._thinking_panel = ThinkingPanel(self)
        thinking_dock = QDockWidget("Thinking (Stub)", self)
        thinking_dock.setObjectName("devDock__thinking")
        thinking_dock.setWidget(self._thinking_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, thinking_dock)
        self.tabifyDockWidget(timing_dock, thinking_dock)

        # Set default active tabs
        vision_dock.raise_()
        scribe_dock.raise_()
        output_dock.raise_()

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
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())
        SHELL_BOUNDS.unregister("dev_inspector")
        DevInspectorWindow._instance = None
        super().closeEvent(event)

    def _update_shell_bounds(self) -> None:
        """Updates absolute screen bounds in SHELL_BOUNDS registry.
        """
        pos = self.pos()
        size = self.size()
        SHELL_BOUNDS.update("dev_inspector", pos.x(), pos.y(), size.width(), size.height())
