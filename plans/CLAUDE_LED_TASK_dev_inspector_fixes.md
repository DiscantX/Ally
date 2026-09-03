# CLAUDE_LED_TASK: Dev Inspector Window — Wiring, Layout, and Stub Fixes

> Corrective pass on the PySide6 GUI rewrite (`plans/CLAUDE_LED_TASK_pyside6_gui_rewrite.md`,
> §8). The dev inspector window currently renders but almost every panel
> stays empty. This is not five separate bugs to hunt down — it is
> overwhelmingly one wiring gap, plus a couple of small independent fixes.
> Read the whole "Root Cause" section before touching code; it explains
> why fixing `dev_window.py`'s `set_core()` call site fixes most of the
> reported symptoms at once.

---

## 0. Root Cause (read this first)

`DevInspectorWindow.__init__` builds `self._bridge = CoreBridge(core, self)`.
`CoreBridge.__init__` → `set_core(core)` connects every `AllyCore.on_x`
`EventHook` to a matching Qt `Signal` on the bridge (e.g.
`core.on_scribe_output.connect(lambda payload: self.scribe_output_ready.emit(payload))`).
That is only *half* the chain.

The other half — connecting `CoreBridge`'s Qt `Signal`s to the actual
panel widgets' slot methods — lives entirely inside
`DevInspectorWindow.set_core()`:

```python
self._bridge.pipeline_image_ready.connect(self._vision_panel.handle_pipeline_image)
self._bridge.debug_overlay_ready.connect(self._debug_panel.handle_debug_overlay)
self._bridge.ocr_result_ready.connect(self._ocr_panel.handle_ocr_result)
self._bridge.scribe_output_ready.connect(self._scribe_panel.handle_scribe_output)
self._bridge.ally_output_ready.connect(self._ally_panel.handle_ally_output)
```

`DevInspectorWindow.__init__` never calls `self.set_core(...)`. The only
caller of `DevInspectorWindow.set_core()` is `main.py`'s
`_on_core_initialized()`, and only conditionally:

```python
if DevInspectorWindow._instance is not None:
    DevInspectorWindow._instance.set_core(loaded_core)
```

In the normal usage pattern — open the dev window from the tray/gear
icon *after* "Ally is online and ready!" appears — the dev window is
constructed fresh, with a valid `core` already available, well after
`_on_core_initialized()` already ran and found `_instance is None`. So
the Signal→panel-slot wiring never happens, for the life of the process,
unless the user happens to open the dev window before core finishes
initializing.

This single gap fully explains the empty Vision Pipeline, Debug Overlay,
OCR/Classification, Scribe (JSON), and Ally (JSON) panels. Entity
Registry, Memory, and Timing Waterfall are poll-based (`QTimer` reading
`self._core` directly, not through the bridge) so they mostly work
already — Entity Registry has its own separate, smaller bug (§2).

**Fix:** the constructor must always finish wiring, regardless of
whether the window was opened early or late.

---

## 1. Fix `interfaces/gui_qt/dev/dev_window.py` wiring

### 1.1 Restructure `CoreBridge` construction to be safely re-callable

In `interfaces/gui_qt/dev/bridge.py`, add an idempotency guard so
`set_core()` can never double-subscribe the same `AllyCore` instance's
`EventHook`s (double subscription would mean every dev panel update
fires twice, and duplicate `lambda` objects would both pass
`EventHook.connect`'s `if callback not in self._subscribers` check since
they're different lambda objects each call):

```python
def __init__(self, core: Optional[AllyCore] = None, parent: Optional[QObject] = None) -> None:
    super().__init__(parent)
    self._wired_core: Optional[AllyCore] = None
    if core is not None:
        self.set_core(core)

def set_core(self, core: AllyCore) -> None:
    if self._wired_core is core:
        return  # already wired to this exact core instance -- no-op
    self._wired_core = core
    core.on_pipeline_image.connect(lambda k, img, t: self.pipeline_image_ready.emit(k, img, t or ""))
    # ... (rest unchanged)
```

### 1.2 Make `DevInspectorWindow.__init__` always finish the wiring

Replace the constructor so it always calls a single `set_core()` path
regardless of whether `core` is `None` at construction time (window
opened too early) or already valid (the normal case):

```python
def __init__(self, core: Optional[AllyCore], theme: Theme, parent: Optional[QWidget] = None) -> None:
    super().__init__(parent)
    self.setObjectName("devInspectorWindow")
    self.setWindowTitle("Ally Dev Inspector")
    self.resize(1400, 900)

    self._core: Optional[AllyCore] = None
    self._theme = theme
    self._bridge = CoreBridge(parent=self)  # do NOT pass core here -- set_core() below handles it
    self._signals_connected = False

    self.setStyleSheet(build_stylesheet(theme, TEMPLATE_PATH))

    self._setup_docks()
    self.setTabPosition(Qt.DockWidgetArea.AllDockWidgetAreas, QTabWidget.TabPosition.North)  # see §3
    self._apply_dock_sizing()  # see §4

    if core is not None:
        self.set_core(core)
```

### 1.3 Make `set_core()` idempotent and complete

Replace the existing `set_core()` body. Guard the Qt Signal→slot
connections with `self._signals_connected` so calling `set_core()` twice
(early-open case: constructor wires it, then `main.py` calls it again
once `_on_core_initialized` runs) never double-connects:

```python
def set_core(self, core: AllyCore) -> None:
    self._core = core
    self._bridge.set_core(core)  # now idempotent, see 1.1
    self._timing_panel._core = core
    self._entity_panel._core = core
    self._memory_panel._core = core

    if not self._signals_connected:
        self._signals_connected = True
        self._bridge.pipeline_image_ready.connect(self._vision_panel.handle_pipeline_image)
        self._bridge.debug_overlay_ready.connect(self._debug_panel.handle_debug_overlay)
        self._bridge.ocr_result_ready.connect(self._ocr_panel.handle_ocr_result)
        self._bridge.scribe_output_ready.connect(self._scribe_panel.handle_scribe_output)
        self._bridge.ally_output_ready.connect(self._ally_panel.handle_ally_output)
        # Thinking panel wiring -- see §5
        self._bridge.thinking_stream_begin.connect(self._thinking_panel.handle_thinking_begin)
        self._bridge.thinking_stream_chunk.connect(self._thinking_panel.handle_thinking_chunk)
        self._bridge.thinking_stream_reset.connect(self._thinking_panel.handle_thinking_reset)
        self._bridge.thinking_stream_finalize.connect(self._thinking_panel.handle_thinking_finalize)

    self._settings = QSettings("Ally", "DevInspectorWindow")
    geometry = self._settings.value("geometry")
    if geometry:
        self.restoreGeometry(geometry)
    state = self._settings.value("windowState")
    if state:
        self.restoreState(state)
```

Note `QSettings` restoration was previously also inside `set_core()` —
keep it there (it's fine to restore geometry/state each time `set_core`
runs; restoring twice is harmless), just don't duplicate it elsewhere.

### 1.4 `main.py` — no changes needed

`main.py`'s existing call —

```python
if DevInspectorWindow._instance is not None:
    DevInspectorWindow._instance.set_core(loaded_core)
```

— is still correct and should stay as-is. It now simply becomes the
"window was opened early" path; the "window opened after core is ready"
path is now handled inside the constructor itself (§1.2).

---

## 2. Fix Entity Registry panel field name

`interfaces/gui_qt/dev/panels/entity_panel.py`, `_poll_entities()`:

```python
name = str(getattr(ent, "name", ""))
```

`Entity` (`brain/state/entity_registry.py`) has no `name` attribute — it
has `canonical_name`. Change to:

```python
name = str(getattr(ent, "canonical_name", ""))
```

---

## 3. Fix dock tabs rendering at the bottom instead of the top

`QMainWindow` never had `setTabPosition` called, so Qt fell back to a
default that puts tab bars at the bottom of tabbed dock groups. Add,
once, right after `_setup_docks()` in `__init__` (already included in
the snippet in §1.2):

```python
self.setTabPosition(Qt.DockWidgetArea.AllDockWidgetAreas, QTabWidget.TabPosition.North)
```

Add `from PySide6.QtWidgets import QTabWidget` to the imports in
`dev_window.py`.

---

## 4. Re-proportion the dock layout — Vision Pipeline should dominate

Currently every dock is added with no explicit sizing, so Qt splits the
left/right/bottom areas roughly evenly, leaving the Vision Pipeline
panel (which needs room for a full screenshot) squeezed into a small
square alongside Debug Overlay and OCR/Classification, which are
tabbed on top of it.

### 4.1 Re-group panels by content type, not arbitrarily

Keep Vision Pipeline and Debug Overlay tabbed together (both are
images, both benefit from the same generous sizing) — but move
OCR/Classification (text) out of that group and tab it with the other
text panels on the right instead:

In `_setup_docks()`:

- **Left area:** Vision Pipeline + Debug Overlay only (tabified with
  each other). Do NOT tabify OCR here.
- **Right area:** Scribe, Ally, Entity Registry, Memory, **and now also
  OCR/Classification** — all tabified together (all are text/table
  panels of comparable size needs).
- **Bottom area:** Timing Waterfall, Output/Logs, Thinking — unchanged
  grouping.

Concretely, change the OCR dock's placement from:

```python
self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, ocr_dock)
self.tabifyDockWidget(vision_dock, ocr_dock)
```

to:

```python
self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, ocr_dock)
self.tabifyDockWidget(scribe_dock, ocr_dock)
```

(`scribe_dock` must already exist above this point in the method —
if the current ordering creates `ocr_dock` before `scribe_dock`, move
the OCR dock's creation block to after the Scribe dock's, or simply
reference whichever right-side dock is created first.)

### 4.2 Explicitly size the left column wider and give it more height priority

Add a helper called once after `_setup_docks()` (already referenced in
§1.2 as `self._apply_dock_sizing()`):

```python
def _apply_dock_sizing(self) -> None:
    """Best-effort initial dock proportions -- QMainWindow only honors
    these as a starting point; QSettings-restored geometry (set_core())
    overrides this on subsequent launches once the user has resized
    docks themselves."""
    self.resizeDocks(
        [self._vision_dock, self._right_column_dock],
        [820, 580],
        Qt.Orientation.Horizontal,
    )
    self.resizeDocks(
        [self._top_row_dock, self._bottom_dock],
        [650, 250],
        Qt.Orientation.Vertical,
    )
```

This requires keeping references to the relevant `QDockWidget` instances
as `self._vision_dock`, `self._right_column_dock` (pick any one dock
from the right-side tab group -- `scribe_dock` is fine), `self._top_row_dock`
(any left/right-area dock works as the vertical-split anchor -- `vision_dock`
is fine, i.e. reuse `self._vision_dock`), and `self._bottom_dock` (any
bottom-area dock, e.g. `timing_dock`). Store these as `self.<name> = <name>_dock`
at the point each is created in `_setup_docks()`, rather than only as
local variables, since `_apply_dock_sizing()` needs to reference them
after `_setup_docks()` returns.

Note: `resizeDocks` is a best-effort hint honored on the *first* real
layout pass, and is overridden the moment `QSettings`-restored geometry
loads in `set_core()` on any run after the first (which is intended --
once the user has manually resized the docks to their liking, respect
that, don't fight it on every launch).

### 4.3 Make the Vision/Debug image labels actually use the space

`VisionPanel`/`DebugPanel` currently `setPixmap()` at native image
resolution inside a `QScrollArea`. For a screenshot-sized image inside a
now-much-larger dock, that's fine as-is (scrollable, no distortion) --
**do not** add auto-scaling/fit-to-width logic in this pass; it's a
reasonable follow-up but out of scope here, since it risks blurring
detail that vision debugging specifically needs to see at full pixel
resolution. Leave `VisionPanel._display_image()` and
`DebugPanel.handle_debug_overlay()` unchanged.

---

## 5. Un-stub the Thinking panel

The original spec correctly deferred this pending research on whether
Gemini's structured-output mode exposes thought summaries. That
research is done and the fix has since shipped (see
`docs/ally_decision_log.md`'s "Provider-Agnostic LLM Base Interface +
Thinking-Stream Parsing Fix" entry) -- `AllyCore.on_thinking_stream_begin/
chunk/reset/finalize` all fire correctly today, and `CoreBridge` already
exposes matching Qt signals (`thinking_stream_begin`, `thinking_stream_chunk`,
`thinking_stream_reset`, `thinking_stream_finalize`). Only the dev-panel
consumer was never built.

Replace `interfaces/gui_qt/dev/panels/thinking_panel.py` entirely:

```python
"""Live thinking-stream dev dock panel.
"""
from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from interfaces.gui_qt.theming.theme import NEUTRAL_CONTENT_THEME


class ThinkingPanel(QWidget):
    """Dock panel displaying Ally's live streamed thinking-trace text.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__thinkingPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._text = QTextEdit(self)
        self._text.setObjectName("devDock__thinkingText")
        self._text.setReadOnly(True)
        self._text.setStyleSheet(
            f"background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; "
            f"color: {NEUTRAL_CONTENT_THEME.fg_secondary}; "
            f"font-family: monospace; font-size: 11px; font-style: italic;"
        )
        self._text.setPlainText("Awaiting thinking stream...")
        layout.addWidget(self._text)

    def handle_thinking_begin(self) -> None:
        """Clears the panel at the start of a new thinking stream.
        """
        self._text.setPlainText("")

    def handle_thinking_chunk(self, chunk: str) -> None:
        """Appends an incoming thinking-stream text chunk.
        """
        cursor = self._text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._text.setTextCursor(cursor)
        self._text.insertPlainText(chunk)

    def handle_thinking_reset(self) -> None:
        """Clears partial thinking text on a mid-stream retry.
        """
        self._text.setPlainText("")

    def handle_thinking_finalize(self) -> None:
        """No-op hook for stream completion -- kept for symmetry with
        the other stream lifecycle handlers and as a seam for a future
        'done thinking' visual state.
        """
        pass
```

Wire it per §1.3's `set_core()` snippet (already included above). No
changes needed to the dock-creation code in `_setup_docks()` beyond
what already exists (`self._thinking_panel = ThinkingPanel(self)` /
`thinking_dock` creation) -- just remove the old stub label text and the
`"Thinking (Stub)"` dock title should become `"Thinking"`.

---

## 6. File Manifest

| Path | Action |
|---|---|
| `interfaces/gui_qt/dev/bridge.py` | Modify — idempotent `set_core()` (§1.1) |
| `interfaces/gui_qt/dev/dev_window.py` | Modify — constructor always wires (§1.2, §1.3), tab position (§3), dock sizing (§4), dock references stored (§4.2), OCR dock regrouped (§4.1) |
| `interfaces/gui_qt/dev/panels/entity_panel.py` | Modify — `ent.name` → `ent.canonical_name` (§2) |
| `interfaces/gui_qt/dev/panels/thinking_panel.py` | Rewrite — real streaming panel (§5) |

---

## 7. Testing Expectations

Manual smoke test (this is unavoidably Qt-widget-heavy, consistent with
the project's existing GUI testing philosophy):

1. Launch `--gui-qt` (or default launch), let core finish initializing
   ("Ally is online and ready!"), **then** open the dev window from the
   tray/gear icon. Confirm Vision Pipeline, Debug Overlay, OCR
   Classification, Scribe, and Ally panels all populate on the very next
   turn -- this is the primary regression case (window opened late).
2. Close the dev window, reopen it. Confirm panels still populate (no
   silent breakage from the idempotency guard swallowing a legitimate
   reconnect).
3. Open the dev window *immediately* on launch, before core finishes
   initializing, and confirm panels still populate once core comes
   online (the early-open path via `main.py`'s existing `set_core` call).
4. Confirm tabs render at the top of each dock group.
5. Confirm Vision Pipeline dock is visibly the largest panel on launch.
6. Confirm Entity Registry table shows real entity names, not a blank
   Name column.
7. Trigger a chat message or gameplay turn and confirm the Thinking
   panel streams live text and clears between turns.

---

## Notes for Claude's Code Review

**ZooCode: ignore this section entirely — it is not part of your task.**

When this comes back, specifically check:

- That `CoreBridge.set_core()`'s idempotency guard compares `is` (object
  identity) not `==` — `AllyCore` doesn't define `__eq__`, so this is
  probably safe either way, but confirm no accidental value-equality
  weirdness was introduced.
- That the constructor path (§1.2) truly never calls `set_core()` twice
  with a *different* concrete lambda set for the Qt Signal→slot half —
  re-read `self._signals_connected` guard placement carefully; it must
  guard the block in `DevInspectorWindow.set_core()`, not
  `CoreBridge.set_core()` (those are two different signal layers with
  two different double-connect risks — EventHook→Signal in the bridge,
  Signal→slot in the window).
- Confirm `_apply_dock_sizing()` doesn't crash if called before docks
  exist, and that the stored dock references (`self._vision_dock` etc.)
  were actually added at dock-creation time in `_setup_docks()`, not
  left as local-only variables.
- Confirm the OCR dock's tabify target was updated consistently — it's
  easy to move `addDockWidget` but forget to also update the
  `tabifyDockWidget` call, leaving it tabified against a stale/wrong
  dock.
- Confirm `thinking_dock`'s display title was updated from
  `"Thinking (Stub)"` to `"Thinking"`.
