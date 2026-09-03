# CLAUDE_LED_TASK: True Edge-Snap Docking Overlay for the Dev Inspector Window

> Follow-up to the dock re-tabbing fix (already applied). This task covers
> the second, larger ask: dragging a panel near the outer edge of the dev
> inspector window should show a VSCode/Visual-Studio-style highlighted
> overlay zone and, on drop, make that panel consume the full span of that
> edge (height for left/right, width for top/bottom) — not just create a
> narrow side-by-side split.
>
> **Read §0 before writing any code.** This is not achievable as a
> lightweight patch on top of `QMainWindow`'s built-in dock system — that
> is explained below, along with why the fix is a library swap rather than
> a custom drag-event hack. Do not attempt to hand-roll drop-zone overlays
> against `QMainWindow`; that path is explicitly rejected in §0.2.

---

## 0. Why this requires a library swap, not a patch

### 0.1 What `QMainWindow` actually gives you

`QMainWindow`'s dock-widget drag/drop machinery is implemented internally
(`QDockAreaLayout`, `QDockWidgetGroupWindow`) with **no public API to
override drop-target computation or draw custom zone overlays**. What you
get today — a thin translucent rectangle previewing where a dock will
land — is Qt's own built-in indicator, not something this app added, and
it cannot be swapped for a bigger VSCode-style zone highlight without
patching Qt itself. There is no `virtual` hook, no signal fired during
the drag with an opportunity to redirect the drop, and no supported way
to say "if the cursor is within N px of the outer edge, ignore the
normal split calculation and claim the whole edge instead."

### 0.2 Why a hand-built overlay-on-top approach is rejected

It is technically possible to install a global event filter, track mouse
position during a `QDockWidget` drag via `topLevelChanged`/window
geometry polling, and paint a translucent `QWidget` overlay on top of the
main window to *visually* suggest a zone. But this cannot actually
**control** where Qt docks the widget on drop — Qt's own internal drop
logic runs independently and will place the widget according to its own
(non-zone-aware) rules regardless of what the overlay drew. The result
would be a highlight that lies about what's about to happen, which is
worse than no highlight at all. **Do not build this.** It's a dead end,
not a smaller version of the real feature.

### 0.3 The actual fix: Qt Advanced Docking System (ADS)

[Qt Advanced Docking System](https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System)
is a mature, actively maintained C++ docking library (used by KDE
Kdenlive, Notepad--, and others) that implements exactly this feature set
natively: large colored edge/center drop-zone overlays during drag,
auto-hide side panels, full re-tabbing, floating windows that themselves
support the same zone overlay, and its own state save/restore. It has an
official PySide6 binding, `PySide6QtAds`.

This task is a **migration** of the dev inspector window's docking layer
from `QMainWindow` + `QDockWidget` to ADS's `CDockManager` +
`CDockWidget`. The panel widgets themselves (`VisionPanel`, `OcrPanel`,
etc.) are unchanged — they're plain `QWidget` subclasses today and stay
that way; only the container/chrome around them changes.

---

## 1. Dependency

Already added to `requirements.txt`:

```
PySide6QtAds
```

Verify at install time (Phase 0, see §2) that this resolves and imports
cleanly in this project's environment before writing any migration code
— pin whatever version successfully installs. If `PySide6QtAds` is
unavailable or broken in this environment for any reason, stop and report
back rather than substituting a different library or reverting to the
rejected hand-built approach from §0.2.

---

## 2. Mandatory Phase 0 — live API verification

Per project convention (see `CLAUDE.md` / `docs/ally_decision_log.md`'s
repeated "Phase 0 live SDK verification is non-negotiable" pattern),
before writing any integration code:

1. `pip install PySide6QtAds` (or add to `requirements.txt` and install),
   confirm import succeeds: `import PySide6QtAds as QtAds`.
2. Write a minimal throwaway script (`tools/ads_smoke_test.py`, fine to
   delete after) that opens a bare `QMainWindow`, creates a
   `QtAds.CDockManager(main_window)`, adds 3–4 dummy `QtAds.CDockWidget`
   instances wrapping plain `QLabel`s, and runs the app. Manually confirm
   in this environment:
   - Dragging a dock widget near the window edge shows the large overlay
     zone and dropping there makes it span the full edge.
   - Re-tabbing by dragging one dock widget onto another's tab strip
     works.
   - `CDockManager.saveState()` / `restoreState(QByteArray)` round-trip
     correctly (save, close, recreate manager, restore, layout matches).
3. Confirm the exact class/method names for this installed version
   (`CDockManager`, `CDockWidget`, `CDockAreaWidget`,
   `addDockWidgetTab`/`addDockWidget`, `DockWidgetArea` enum values —
   API has shifted slightly across ADS versions; verify against what's
   actually installed, don't assume from memory/documentation alone).
4. Document what was verified as a code comment at the top of the new
   `interfaces/gui_qt/dev/dev_window.py` (see §3) — one or two lines,
   same pattern as the existing Interactions API verification comments
   in `infrastructure/llm/providers/gemini_provider.py`.

**Bail-out condition:** if step 2's smoke test does not show true
edge-zone overlay behavior on this specific installed version (e.g. an
older ADS release behaves differently than documented), stop and report
back with what was actually observed rather than proceeding on
assumption.

---

## 3. Migration: `interfaces/gui_qt/dev/dev_window.py`

### 3.1 Replace the dock container

Currently `DevInspectorWindow(QMainWindow)` uses
`self.addDockWidget(...)` / `self.tabifyDockWidget(...)` directly on
itself. Replace with:

```python
import PySide6QtAds as QtAds

class DevInspectorWindow(QMainWindow):
    def __init__(self, core, theme, parent=None):
        super().__init__(parent)
        ...
        self._dock_manager = QtAds.CDockManager(self)
        ...
```

`CDockManager` takes over as the central widget's docking host — do not
also keep `QMainWindow`'s native `addDockWidget`/`QDockWidget` calls
alongside it; this is a full replacement of the docking layer, not an
addition.

### 3.2 Convert each panel from `QDockWidget` to `CDockWidget`

For each of the ten panels currently wrapped like:

```python
self._vision_panel = VisionPanel(self)
vision_dock = QDockWidget("Vision Pipeline", self)
vision_dock.setObjectName("devDock__vision")
vision_dock.setWidget(self._vision_panel)
self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, vision_dock)
```

convert to:

```python
self._vision_panel = VisionPanel(self)
vision_dock = QtAds.CDockWidget("Vision Pipeline")
vision_dock.setObjectName("devDock__vision")
vision_dock.setWidget(self._vision_panel)
self._dock_manager.addDockWidget(QtAds.DockWidgetArea.LeftDockWidgetArea, vision_dock)
```

Preserve every existing `objectName` string exactly (`devDock__vision`,
`devDock__debug`, `devDock__ocr`, `devDock__scribe`, `devDock__ally`,
`devDock__entity`, `devDock__memory`, `devDock__timing`,
`devDock__output`, `devDock__thinking`) — these are referenced by
`docs/THEMING.md`'s documented naming convention and may be targeted by
QSS; do not rename them as part of this migration.

Re-create the existing tab groupings using ADS's equivalent of
`tabifyDockWidget` (verify exact method name/signature in Phase 0 — ADS
typically exposes this via `addDockWidgetTab` or by passing an existing
`CDockAreaWidget` as a target to `addDockWidget`, confirm which):

- Left: Vision Pipeline + Debug Overlay, tabbed together.
- Right: Scribe, Ally, Entity Registry, Memory, OCR/Classification, all
  tabbed together (per the existing regrouping from the prior dock-fixes
  task — preserve that grouping, do not revert to the original spec's
  grouping).
- Bottom: Timing Waterfall, Output/Logs, Thinking, tabbed together.

### 3.3 Layout persistence

Replace the existing `QSettings`-based `saveGeometry()`/`restoreGeometry()`/
`saveState()`/`restoreState()` calls (which were `QMainWindow`-native dock
state) with ADS's own persistence:

```python
# on close:
self._settings.setValue("adsState", self._dock_manager.saveState())
self._settings.setValue("geometry", self.saveGeometry())  # window geometry itself is still plain QMainWindow/QWidget, keep as-is

# on set_core() / restore:
state = self._settings.value("adsState")
if state:
    self._dock_manager.restoreState(state)
```

Keep the same `QSettings("Ally", "DevInspectorWindow")` key/org — only
the *value* being saved for dock layout changes from `QMainWindow`'s
format to ADS's; the outer `QSettings` object and the plain window
geometry save/restore are unaffected.

### 3.4 Dock sizing

`_apply_dock_sizing()`'s `self.resizeDocks(...)` calls are `QMainWindow`
API and will not work against `CDockManager`-owned areas. Replace with
ADS's equivalent for setting initial split proportions (verify exact API
in Phase 0 — likely `CDockAreaWidget.setSplitterSizes` or setting size
hints when calling `addDockWidget` with a target area). Preserve the
existing intent: Vision Pipeline column wider than the right column,
top row taller than the bottom row. Exact pixel values may need
re-tuning once real edge-zone drops make the panels span differently
than before — that's expected, tune by eye during manual testing (§6),
not by trying to replicate the old `QMainWindow` numbers exactly.

### 3.5 Theming

`self.setStyleSheet(build_stylesheet(theme, TEMPLATE_PATH))` currently
styles `QMainWindow`'s native dock chrome via the object names in
`base.qss.tmpl`. ADS renders its own dock chrome (title bars, tab
widgets, splitters) with **different internal widget/class names** that
this project's existing QSS selectors will not match. Two things need to
happen:

1. Verify in Phase 0 what ADS actually exposes for styling — it ships
   its own default stylesheet and documents the QSS selectors/class
   names it uses (e.g. `#dockManager`, `ads--CDockWidgetTab`, etc. —
   confirm exact names against the installed version, do not guess from
   memory).
2. Add ADS-specific selector rules to `interfaces/gui_qt/theming/base.qss.tmpl`
   using the *same token values* already defined per-theme (`{bg_surface}`,
   `{accent_primary}`, etc.) so ADS's chrome still follows the active
   `Signal`/`Synthwave` theme, consistent with `docs/THEMING.md`'s
   existing "dev-window chrome follows the active user theme, content
   areas use `NEUTRAL_CONTENT_THEME`" rule. Do not hardcode new colors —
   reuse the template's existing `{token}` placeholders.

Update `docs/THEMING.md` with a short new subsection noting that dev
inspector dock chrome is now rendered by Qt Advanced Docking System and
styled via its own QSS selector set (list the selectors actually used),
still following the same token system.

### 3.6 Everything else stays as-is

Do **not** change:

- `CoreBridge` (`interfaces/gui_qt/dev/bridge.py`) — panel data wiring is
  independent of the docking container.
- Any panel widget's internals (`VisionPanel`, `OcrPanel`, `ScribePanel`,
  etc.) — they remain plain `QWidget`s, unaware of whether they're hosted
  in a `QDockWidget` or a `CDockWidget`.
- Self-capture exclusion (`showEvent`/`moveEvent`/`resizeEvent` calling
  `exclude_hwnd_from_capture` and `SHELL_BOUNDS.update`) — this operates
  on the top-level `DevInspectorWindow`'s own geometry, not on individual
  docks, and is unaffected by the docking-layer swap.
- The singleton pattern (`get_instance()`), `set_core()`'s idempotency
  guards, or the `CoreBridge` signal-connection guard (`_signals_connected`)
  from the prior dock-fixes task — all of that logic is orthogonal to
  which docking library owns the layout.

---

## 4. `QMainWindow.DockOption` cleanup

Once the migration lands, the existing `self.setDockOptions(...)` call
(now on a `QMainWindow` that no longer hosts native docks directly, since
`CDockManager` owns that) becomes dead code — remove it, since
`QMainWindow.DockOption` has no effect once `CDockManager` is the actual
docking host. Do not leave it in "just in case."

---

## 5. File Manifest

| Path | Action |
|---|---|
| `requirements.txt` | Modify — add `PySide6QtAds` (§1) |
| `interfaces/gui_qt/dev/dev_window.py` | Modify — replace `QMainWindow` native docking with `CDockManager`/`CDockWidget` throughout (§3) |
| `interfaces/gui_qt/theming/base.qss.tmpl` | Modify — add ADS-specific selector rules using existing theme tokens (§3.5) |
| `docs/THEMING.md` | Modify — document ADS chrome styling (§3.5) |
| `tools/ads_smoke_test.py` | New, throwaway — Phase 0 verification script (§2), fine to delete once verification is complete and documented |

---

## 6. Testing Expectations

Manual smoke test (unavoidably Qt-widget-heavy, consistent with project
convention — this feature is inherently about drag gesture UX that
doesn't reduce to a meaningful automated test):

1. Launch the dev inspector window. Confirm the same ten panels appear,
   grouped into the same three tab clusters (Left: Vision+Debug; Right:
   Scribe/Ally/Entity/Memory/OCR; Bottom: Timing/Output/Thinking) as
   before the migration.
2. Drag a panel's tab out to float it, then drag it near the **outer
   left edge** of the window (not onto an existing dock). Confirm a
   large, clearly visible overlay zone appears highlighting the full
   left edge, and dropping there makes the panel span the full window
   height on the left.
3. Repeat for right, top, and bottom edges.
4. Drag a floated panel onto an **existing tab group's** tab strip.
   Confirm it still tabs in correctly (this must keep working — it's
   the fix from the prior task, now running through ADS instead of
   native Qt docking).
5. Close and relaunch the dev inspector window. Confirm the dock layout
   (including any edge-snapped panels from steps 2–4, if left in that
   state) restores correctly via `CDockManager.restoreState()`.
6. Confirm dev-window chrome (title bars, tab highlights, splitters)
   still follows the active theme (`Signal` vs `Synthwave`) after
   switching themes in settings, and that panel *content* areas
   (`VisionPanel`'s JSON/image views, etc.) still render with
   `NEUTRAL_CONTENT_THEME` regardless of the active user theme.
7. Confirm self-capture exclusion still works — the dev inspector window
   itself must not appear in Ally's own screen captures when positioned
   over the game window (same check as before this migration, just
   re-verify it wasn't broken by the docking-layer swap).
8. Confirm the prod overlay window (`interfaces/gui_qt/prod/`) is
   completely unaffected — this migration is scoped to the dev inspector
   window only.

---

## Notes for Claude's Code Review

**ZooCode: ignore this section entirely — it is not part of your task.**

- Confirm §0.2's rejected approach wasn't quietly built anyway as a
  fallback "in case ADS doesn't work out" — if ADS integration hit a
  wall, the right move was to stop and report back (per §2's bail-out
  condition), not to silently degrade to a fake overlay.
- Confirm the Phase 0 smoke test actually ran and its findings are
  documented as a comment in `dev_window.py`, not skipped — per the
  project's standing "Phase 0 verification is non-negotiable" rule, and
  because ADS's Python API has shifted across versions historically, so
  a working call today could be verified against a stale API from
  training data rather than what's actually installed.
- Check that every one of the ten panel `objectName`s was preserved
  exactly — easy to accidentally rename during the `QDockWidget` →
  `CDockWidget` conversion since it's a lot of repetitive boilerplate.
- Check that `CoreBridge` and the panels' own signal wiring were left
  completely untouched — if ZooCode touched `bridge.py` or any panel's
  `handle_*` methods, that's scope creep; this task is purely about the
  container.
- Verify the QSS additions for ADS chrome actually reference `{token}`
  placeholders from the existing `Theme` dataclass rather than
  hardcoded hex values — a copy-pasted example from ADS's own docs
  might bring literal colors that don't move with theme switching.
- Confirm `requirements.txt`'s new entry pins a version if the smoke
  test needed a specific one to get working edge-zone behavior — don't
  leave it unpinned if a particular version was load-bearing.
- If `_apply_dock_sizing()`'s replacement produces visibly different
  proportions than before, that's expected per §3.4 — don't flag it as
  a bug unless it's unusable (e.g. a panel collapsed to near-zero size).
