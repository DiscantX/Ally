# Dev Inspector Phase 2 Plan: Adjustable Text Size and Scaling

## Objective
Implement adjustable text size and font scaling for the Dev Inspector window (`DevInspectorWindow`), persisting the scale multiplier in `QSettings("Ally", "DevInspectorWindow")` under `"devFontScale"`, wiring it into the stylesheet generator via font size tokens (`{dev_font_size_11}`, `{dev_font_size_10}`), and ensuring independent persistence between themes and text sizes.

---

## Discrete Subtasks

### 2.1 — Create Phase 2 Detailed Plan (`plans/dev_inspector_phase2_plan.md`)
- [x] Write comprehensive plan detailing menus, scaling logic, QSettings persistence, and verification criteria.

### 2.2 — Update Theme and Stylesheet Generator (`interfaces/gui_qt/theming/theme.py` & `base.qss.tmpl`)
- [1] Update `build_stylesheet()` to accept `dev_font_scale: float = 1.0`.
- [2] Compute proportional font sizes (e.g., base 11pt and base 10pt multiplied by `dev_font_scale`).
- [3] Update `base.qss.tmpl` dev panel rules to use `{dev_font_size_11}` and `{dev_font_size_10}`.

### 2.3 — Implement Text Size Menu and Custom Dialog in `DevInspectorWindow` (`interfaces/gui_qt/dev/dev_window.py`)
- [1] Add **"View" menu → "Text Size"** submenu.
- [2] Add preset actions with radio buttons / exclusive checkable actions:
  - **Smallest** (`0.75x`)
  - **Small** (`0.85x`)
  - **Medium (Default)** (`1.0x`)
  - **Large** (`1.2x`)
  - **Largest** (`1.4x`)
- [3] Add **"Custom..."** action triggering a `QDialog` with a `QSpinBox` (bounds 6–24 pt) computing scale as `pt / 11.0`.
- [4] Persist `devFontScale` via `QSettings("Ally", "DevInspectorWindow")`.

### 2.4 — Wire Dynamic Stylesheet Rebuild & Theme Independence
- [1] Implement a shared `_rebuild_dev_stylesheet()` method in `DevInspectorWindow` that loads the active theme and current `devFontScale`, generates the stylesheet, and applies it to the window.
- [2] Ensure switching themes does not reset text size, and changing text size does not reset theme.

### 2.5 — Verification & Testing
- [1] Verify presets and custom point sizes dynamically resize dev panels.
- [2] Verify persistence across close/reopen.
- [3] Verify independence of theme and text size selections.
