# Phase 0 Verification Plan: Dev Inspector Theming and Views

Refer to [`plans/CLAUDE_LED_TASK_dev_inspector_theming_and_views.md`](plans/CLAUDE_LED_TASK_dev_inspector_theming_and_views.md).

## Overview
Phase 0 establishes foundational verification gates before any integration or refactoring code is written:
1. **xterm-256 → Hex Conversion Validation**: Programmatically convert xterm-256 color index codes found in [`infrastructure/logger/logger.py`](infrastructure/logger/logger.py) to 24-bit RGB hex values, specifically cross-checking indices 208, 128, and 121 against published xterm-256 color charts.
2. **PySide6 QSS Dynamic Property Selector Verification**: Test whether PySide6 `6.11.1` successfully evaluates dynamic property QSS selectors (`QWidget[themed="devPanel"]`).

---

## Subtask 0.1: xterm-256 → Hex Conversion

### Algorithm
- **6x6x6 Color Cube (Indices 16–231)**:
  - For index `n`: `i = n - 16`
  - `r_idx = i // 36`
  - `g_idx = (i % 36) // 6`
  - `b_idx = i % 6`
  - Channel value: `0` if index is `0`, else `55 + 40 * index`.
  - Convert to hex: `f"#{r:02x}{g:02x}{b:02x}"`.
- **Grayscale Ramp (Indices 232–255)**:
  - `v = 8 + 10 * (n - 232)` for all three channels R, G, B.
  - Convert to hex: `f"#{v:02x}{v:02x}{v:02x}"`.

### Key Indices to Cross-Check
- **Index 208**: Expected hex `#ff8700` (or rgb(255, 135, 0)) — orange.
- **Index 128**: Expected hex `#875f87` (or rgb(135, 95, 135)) — purple.
- **Index 121**: Expected hex `#87ffaf` (or rgb(135, 255, 175)) — mint.

### Bail-out Condition
If any computed value does not match published charts, stop before Phase 1 and report the discrepancy.

---

## Subtask 0.2: Qt QSS Selector Mechanism (`pyside6==6.11.1`)

### Test Case
1. Create a `QApplication` instance.
2. Create a test `QWidget`, call `widget.setProperty("themed", "devPanel")`.
3. Apply stylesheet: `QWidget[themed="devPanel"] { background-color: rgb(255, 0, 0); }`.
4. Force polish/style update if needed and verify `widget.palette()` or rendered background color matches red (`rgb(255, 0, 0)`).

### Decision Rule
- If dynamic property selectors work (expected), proceed with dynamic properties for QSS centralization in Phase 1.
- If dynamic property selectors fail, stop and report back for scope re-evaluation.

---

## Execution Scripts
- [`tooling/tools/debug_xterm256_conversion.py`](tooling/tools/debug_xterm256_conversion.py)
- [`tooling/tools/debug_qt_qss_selector.py`](tooling/tools/debug_qt_qss_selector.py)
