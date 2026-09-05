"""Ally JSON tree view and detail pane dev dock panel.
"""
from typing import Optional, Any
import json
from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QTreeView, QTextEdit
from interfaces.gui_qt.theming.theme import Theme, SLATE
from interfaces.gui_qt.dev.json_tree_model import JsonTreeModel


class AllyPanel(QWidget):
    """Dock panel displaying AllyOutput as a hierarchical QTreeView with a detail pane.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__allyPanel")
        self._theme: Theme = SLATE
        self._last_raw_data: Any = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Vertical splitter: Tree on top, detail pane below
        self._splitter = QSplitter(Qt.Orientation.Vertical, self)
        layout.addWidget(self._splitter)

        # Top: QTreeView backed by JsonTreeModel
        self._tree_view = QTreeView(self)
        self._tree_view.setObjectName("devDock__allyTree")
        self._tree_view.setHeaderHidden(False)
        self._tree_view.setAlternatingRowColors(True)
        self._splitter.addWidget(self._tree_view)

        # Bottom: QTextEdit detail pane
        self._detail_text = QTextEdit(self)
        self._detail_text.setObjectName("devDock__allyDetail")
        self._detail_text.setReadOnly(True)
        self._detail_text.setWordWrapMode(Qt.TextWrapMode.WordWrap)
        self._detail_text.setProperty("themed", "devPanelText")
        self._detail_text.setPlainText("Awaiting Ally output...")
        self._splitter.addWidget(self._detail_text)

        # Set initial splitter proportions (e.g. 60% tree, 40% detail)
        self._splitter.setSizes([300, 200])

        # Initial empty model
        empty_model = JsonTreeModel({}, theme=self._theme, parent=self)
        self._tree_view.setModel(empty_model)
        self._tree_view.setColumnWidth(0, 200)
        if self._tree_view.header():
            self._tree_view.header().setStretchLastSection(True)

        # Connect selection change
        self._tree_view.selectionModel().currentChanged.connect(self._on_current_changed)

    def set_active_theme(self, theme: Theme) -> None:
        """Updates the active theme and refreshes the tree model and detail pane.
        """
        self._theme = theme
        if self._last_raw_data is not None:
            self.handle_ally_output(self._last_raw_data)
        else:
            model = JsonTreeModel({}, theme=self._theme, parent=self)
            self._tree_view.setModel(model)
            self._tree_view.setColumnWidth(0, 200)

    def _on_current_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not current.isValid():
            self._detail_text.setPlainText("Select a node above to see its full value.")
            return
        model = self._tree_view.model()
        if isinstance(model, JsonTreeModel):
            full_val = model.full_value_for_index(current)
            self._detail_text.setPlainText(full_val)
        else:
            self._detail_text.setPlainText("")

    def handle_ally_output(self, output: Any) -> None:
        """Receives AllyOutput (or None) and displays it in the JSON tree and detail pane.
        """
        self._last_raw_data = output
        if output is None:
            model = JsonTreeModel({}, theme=self._theme, parent=self)
            self._tree_view.setModel(model)
            self._detail_text.setPlainText("(No Ally output)")
            return

        try:
            if hasattr(output, "model_dump"):
                data = output.model_dump()
            elif hasattr(output, "dict"):
                data = output.dict()
            elif isinstance(output, (dict, list)):
                data = output
            else:
                data = {"value": str(output)}

            model = JsonTreeModel(data, theme=self._theme, parent=self)
            self._tree_view.setModel(model)
            self._tree_view.expandToDepth(0)
            self._tree_view.setColumnWidth(0, 200)
            if self._tree_view.header():
                self._tree_view.header().setStretchLastSection(True)

            self._detail_text.setPlainText("Select a node above to see its full value.")
            self._tree_view.selectionModel().currentChanged.connect(self._on_current_changed)
        except Exception as e:
            model = JsonTreeModel({"error": str(e), "raw": str(output)}, theme=self._theme, parent=self)
            self._tree_view.setModel(model)
            self._tree_view.expandToDepth(0)
            self._detail_text.setPlainText(f"Error formatting Ally output: {e}")
