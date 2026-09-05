# Dev Inspector Phase 3 Plan: JSON Tree View & Detail Pane

## Objectives
1. Implement `JsonTreeModel` (`interfaces/gui_qt/dev/json_tree_model.py`) subclassing `QAbstractItemModel` for hierarchical JSON data visualization with theme-aware coloring, type/count summaries, scalar truncation, and untruncated detail lookup.
2. Redesign `ScribePanel` (`interfaces/gui_qt/dev/panels/scribe_panel.py`) and `AllyPanel` (`interfaces/gui_qt/dev/panels/ally_panel.py`) using a vertical `QSplitter`, `QTreeView` (auto-expanding depth 0), and a read-only detail `QTextEdit`.
3. Support dynamic theme updates via `set_active_theme(theme: Theme)` on both panels and model re-creation.
4. Preserve fallback / skipped / awaiting placeholder UX.

## Subtasks
1. **`JsonTreeModel` implementation (`interfaces/gui_qt/dev/json_tree_model.py`)**:
   - Define `_JsonNode` dataclass (`key`, `value`, `parent`, `children`).
   - Implement `_build_tree()` recursive helper to build nodes from dicts, lists, and scalars.
   - Implement `columnCount()` (2), `headerData()` ("Key", "Value").
   - Implement `rowCount()`, `index()`, `parent()`.
   - Implement `data()` handling `Qt.ItemDataRole.DisplayRole` (Key / summary / truncated scalar) and `Qt.ItemDataRole.ForegroundRole` (theme-aware colors for keys, strings, numbers, booleans/nulls, summaries).
   - Implement `full_value_for_index(index: QModelIndex) -> str` returning raw scalar or pretty-printed JSON subtree.

2. **Panel Redesign (`ScribePanel` & `AllyPanel`)**:
   - Set up vertical `QSplitter`.
   - Add `QTreeView` with `JsonTreeModel`, set column widths (`expandToDepth(0)`).
   - Add read-only detail `QTextEdit` below.
   - Connect `currentChanged` selection signal to update detail pane with `full_value_for_index()`.
   - Cache raw output to allow rebuilding model on theme change.
   - Handle `None` / skipped states cleanly in detail pane and tree.

3. **Theme Integration**:
   - Add `set_active_theme(theme: Theme)` to both panels.
   - Call from `DevInspectorWindow._apply_active_theme()`.
   - Rebuild model with updated theme colors.

4. **Verification**:
   - Run tests / verify syntax and functionality.
