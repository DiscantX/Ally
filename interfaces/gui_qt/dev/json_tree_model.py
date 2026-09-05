"""QAbstractItemModel implementation for hierarchical JSON data visualization
in Dev Inspector panels (Scribe and Ally).
"""
from typing import Any, Optional, Union
from dataclasses import dataclass, field
import json
from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex
from PySide6.QtGui import QColor
from interfaces.gui_qt.theming.theme import Theme, SLATE


@dataclass
class _JsonNode:
    key: Union[str, int, None]
    value: Any
    parent: Optional["_JsonNode"] = None
    children: list["_JsonNode"] = field(default_factory=list)


class JsonTreeModel(QAbstractItemModel):
    """QAbstractItemModel wrapping Python dict/list/scalar data structures
    for display in a QTreeView with two columns (Key, Value), type/count summaries,
    scalar truncation, and theme-aware coloring.
    """
    def __init__(self, data: Any, theme: Theme = SLATE, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._root = _JsonNode(key=None, value=data, parent=None)
        self._build_tree(self._root)

    def _build_tree(self, node: _JsonNode) -> None:
        val = node.value
        if isinstance(val, dict):
            for k, v in val.items():
                child = _JsonNode(key=str(k), value=v, parent=node)
                node.children.append(child)
                self._build_tree(child)
        elif isinstance(val, (list, tuple)):
            for idx, v in enumerate(val):
                child = _JsonNode(key=idx, value=v, parent=node)
                node.children.append(child)
                self._build_tree(child)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            parent_node = self._root
        else:
            parent_node = parent.internalPointer()
        return len(parent_node.children)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 2

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parent_node = self._root
        else:
            parent_node = parent.internalPointer()

        if 0 <= row < len(parent_node.children):
            child_node = parent_node.children[row]
            return self.createIndex(row, column, child_node)
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        child_node: _JsonNode = index.internalPointer()
        if child_node is None or child_node.parent is None:
            return QModelIndex()

        parent_node = child_node.parent
        if parent_node == self._root:
            return QModelIndex()

        # Find row of parent_node among grandparent's children
        grandparent = parent_node.parent
        if grandparent is None:
            return QModelIndex()

        try:
            row = grandparent.children.index(parent_node)
            return self.createIndex(row, 0, parent_node)
        except ValueError:
            return QModelIndex()

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section == 0:
                return "Key"
            elif section == 1:
                return "Value"
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None

        node: _JsonNode = index.internalPointer()
        if node is None:
            return None

        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                if node.key is None:
                    return "(root)"
                return str(node.key)
            elif col == 1:
                val = node.value
                if isinstance(val, dict):
                    n = len(val)
                    key_str = "keys" if n != 1 else "key"
                    return f"{{{n} {key_str}}}"
                elif isinstance(val, (list, tuple)):
                    n = len(val)
                    item_str = "items" if n != 1 else "item"
                    return f"[{n} {item_str}]"
                else:
                    text = str(val)
                    if len(text) > 80:
                        text = text[:77] + "..."
                    return text

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 0:
                return QColor(self._theme.accent_secondary)
            else:
                val = node.value
                if isinstance(val, dict) or isinstance(val, (list, tuple)):
                    return QColor(self._theme.fg_muted)
                elif isinstance(val, str):
                    return QColor(self._theme.fg_primary)
                elif isinstance(val, (int, float)):
                    return QColor(self._theme.success)
                elif isinstance(val, bool) or val is None:
                    return QColor(self._theme.warning)
                else:
                    return QColor(self._theme.fg_primary)

        return None

    def full_value_for_index(self, index: QModelIndex) -> str:
        """Returns the untruncated string representation of a node's value.
        For scalars: str(value). For dict/list: pretty-printed JSON.
        """
        if not index.isValid():
            return ""
        node: _JsonNode = index.internalPointer()
        if node is None:
            return ""

        val = node.value
        if isinstance(val, (dict, list, tuple)):
            try:
                return json.dumps(val, indent=2, default=str)
            except Exception as e:
                return f"{val} (Error formatting JSON: {e})"
        else:
            return str(val)
