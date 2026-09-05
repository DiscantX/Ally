# Phase 1 Implementation Plan: `theming/` Package, Slate Theme, Logger Rewire, Dev Window Theme Menu, and QSS Centralization

This plan outlines the specific steps for executing Phase 1 of [`plans/CLAUDE_LED_TASK_dev_inspector_theming_and_views.md`](plans/CLAUDE_LED_TASK_dev_inspector_theming_and_views.md:103).

## Subtasks

1. **Create Detailed Plan**: Write [`plans/dev_inspector_phase1_plan.md`](plans/dev_inspector_phase1_plan.md:1).
2. **Create Top-Level `theming/` Package**:
   - [`theming/__init__.py`](theming/__init__.py:1)
   - [`theming/color_convert.py`](theming/color_convert.py:1) with `hex_to_ansi_fg` and `ansi_fg_to_hex` (supporting 24-bit and xterm-256 indexed with `N < 16` validation).
   - [`theming/palettes.py`](theming/palettes.py:1) with `THEME_MODULE_COLORS`, `THEME_MODULE_PALETTE_HUES`, `THEME_LEVEL_COLORS`, and `resolve_module_color()`.
   - Unit tests in [`tests/test_color_convert.py`](tests/test_color_convert.py:1).
3. **Update [`interfaces/gui_qt/theming/theme.py`](interfaces/gui_qt/theming/theme.py:1)**:
   - Rename `NEUTRAL_CONTENT_THEME` to `SLATE` with deprecated alias `NEUTRAL_CONTENT_THEME = SLATE`.
   - Extend `Theme` dataclass with `font_mono`, `module_log_colors`, `log_level_colors`.
   - Populate instances (`SLATE`, `SIGNAL`, `SYNTHWAVE`).
4. **Rewire [`infrastructure/logger/logger.py`](infrastructure/logger/logger.py:1)**:
   - Remove `COLORS` dict and per-entry color keys from `REGISTRY`.
   - Populate `THEME_MODULE_COLORS["Slate"]` with exact hex values.
   - Use `theming.palettes.resolve_module_color()` and `hex_to_ansi_fg()` in `resolve_module_info()` and `log()`.
5. **Add Theme Menu & Persistence in [`interfaces/gui_qt/dev/dev_window.py`](interfaces/gui_qt/dev/dev_window.py:1)**:
   - Add mutually exclusive Theme actions (Slate, Signal, Synthwave) in a Theme menu via `QActionGroup`.
   - Persist theme selection in `QSettings("Ally", "DevInspectorWindow")` under key `"devThemeName"`, defaulting to `"Slate"`.
   - Implement `_apply_active_theme()` and propagate to panels.
6. **Centralize QSS across 10 Dev Panels**:
   - Update [`interfaces/gui_qt/theming/base.qss.tmpl`](interfaces/gui_qt/theming/base.qss.tmpl:1) with rules for `themed` dynamic properties (`devPanelText`, `devPanelTable`, `devPanelSurface`, `devPanelTitle`) and `level` dynamic properties.
   - Remove inline `setStyleSheet(...)` calls from the 10 dev panels (`timing_panel.py`, `ally_panel.py`, `ocr_panel.py`, `entity_panel.py`, `scribe_panel.py`, `debug_panel.py`, `memory_panel.py`, `output_panel.py`, `vision_panel.py`, `thinking_panel.py`) and replace with `setProperty("themed", ...)` + polish.
7. **Update GUI Log Panels**:
   - Update `OutputPanel`, `MemoryPanel`, and `VisionPanel` to render rich HTML log lines utilizing active theme's module and log level colors.
   - Support live re-rendering on theme switch via `set_active_theme()`.
8. **Verification & Testing**:
   - Run unit tests and verify terminal output and GUI functionality.
