# Phase 4 Plan — OCR Panel Redesign & Documentation Updates

## 1. Objectives
- Redesign [`interfaces/gui_qt/dev/panels/ocr_panel.py`](interfaces/gui_qt/dev/panels/ocr_panel.py:1) to replace the single text dump with a structured header strip and sortable `QTableWidget`.
- Ensure proper themed roles (`"devPanelTitle"`, `"devPanelTable"`, etc.) and live theme updating via `set_active_theme()`.
- Update all required documentation files: [`docs/ally_decision_log.md`](docs/ally_decision_log.md:1), [`docs/changelog.md`](docs/changelog.md:1), [`docs/roadmap.md`](docs/roadmap.md:1), and [`docs/THEMING.md`](docs/THEMING.md:1).
- Run full test suite and verify completion.

## 2. Subtasks

### 2.1 OCR Panel Redesign (`OcrPanel`)
- Header strip (`QHBoxLayout` or `QFormLayout` / vertical layout of labeled fields):
  - Screen Name
  - Confidence (`{:.2f}`)
  - Is Draft Match (Yes/No or boolean display)
  - Screen Category
  - Skip Reason
- Apply `"devPanelTitle"` themed role to header labels.
- `QTableWidget` for confirmed facts with columns: `Key` / `Value` / `Source`.
- Enable sorting via `setSortingEnabled(True)`.
- Apply `"devPanelTable"` themed role and table styling matching [`interfaces/gui_qt/dev/panels/entity_panel.py`](interfaces/gui_qt/dev/panels/entity_panel.py:1).
- Implement `set_active_theme(theme: Theme)` method to update table stylesheet and label colors on theme change.
- Cache last OCR payload in `self._last_payload` to re-render correctly when theme changes.

### 2.2 Dev Inspector Window Integration
- Update [`interfaces/gui_qt/dev/dev_window.py`](interfaces/gui_qt/dev/dev_window.py:1) to initialize [`interfaces/gui_qt/dev/panels/ocr_panel.py`](interfaces/gui_qt/dev/panels/ocr_panel.py:1) with the active theme and update it in `set_active_theme()`.

### 2.3 Documentation Updates
- [`docs/ally_decision_log.md`](docs/ally_decision_log.md:1): Architectural decisions (`theming/` package rationale, `Slate` rename, exact-vs-hashed module color resolution, dynamic property QSS decision, terminal hardcoded Slate scope).
- [`docs/changelog.md`](docs/changelog.md:1): Routine changelog entry for Phase 1-4 and documentation.
- [`docs/roadmap.md`](docs/roadmap.md:1): Remove resolved items, add terminal theme switching deferred.
- [`docs/THEMING.md`](docs/THEMING.md:1): Living reference update for `Slate`, `theming/` package, new `Theme` fields, Theme menu, and text size.

### 2.4 Testing & Verification
- Run pytest suite across [`tests/`](tests/:1).
- Verify live execution and UI responsiveness.
