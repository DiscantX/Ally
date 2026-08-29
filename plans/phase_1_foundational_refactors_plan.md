# Phase 1 — Foundational Refactors Implementation Plan

This document outlines the detailed execution plan for Phase 1 (Foundational Refactors) of the PySide6 GUI rewrite, derived directly from [`plans/CLAUDE_LED_TASK_pyside6_gui_rewrite.md`](plans/CLAUDE_LED_TASK_pyside6_gui_rewrite.md).

---

## 1. Overview & Architectural Principles

Phase 1 establishes the multi-subscriber event messaging foundation, telemetry snapshot ring buffer, logger pub/sub channel routing, and self-capture exclusion safeguards needed before implementing the PySide6 GUI shells (Prod Overlay & Dev Inspector Window).

Key architecture principles:

- **GUI-Agnostic Air-Gap**: [`AllyCore`](brain/reasoning/core.py), [`infrastructure/logger/logger.py`](infrastructure/logger/logger.py), and [`utils/event_hook.py`](utils/event_hook.py) remain 100% GUI-framework-agnostic with zero imports of PySide6 or Tkinter.
- **Synchronous Execution & Threading Safety**: [`EventHook.emit()`](utils/event_hook.py) executes callbacks synchronously on the calling thread. Qt consumers in later phases will bridge these into Qt signals via `CoreBridge` rather than touching widgets directly.
- **Fail-Safe Observer Invocations**: Subscriber exceptions inside [`EventHook.emit()`](utils/event_hook.py) or logger subscriber notifications are caught and logged, preventing broken subscribers from taking down the core loop or logger.
- **Dual-Layer Self-Capture Exclusion**: Both Windows DWM API (`SetWindowDisplayAffinity`) and unconditional software blackout masking via [`ShellBoundsRegistry`](brain/state/shell_bounds_registry.py) in [`ScreenCollector.capture_bgr()`](ingestion/collectors/screen_collector.py) operate simultaneously.

---

## 2. Detailed Deliverables & Step-by-Step Tasks

### Task 1.1: Multi-Subscriber [`EventHook`](utils/event_hook.py) Utility

- **Target File**: [`utils/event_hook.py`](utils/event_hook.py)
- **Design & Requirements**:
  - Implement class [`EventHook`](utils/event_hook.py) with methods `__init__(name: str = "")`, `connect(callback: Callable) -> None`, `disconnect(callback: Callable) -> None`, and `emit(*args, **kwargs) -> None`.
  - In `connect()`, check if `callback not in self._subscribers` before appending to prevent duplicate callbacks.
  - In `disconnect()`, check membership before removing to avoid `ValueError`.
  - In `emit()`, iterate over a shallow copy (`list(self._subscribers)`) so dynamic disconnections during execution do not mutate the iterated list.
  - Wrap each callback invocation in `try...except Exception as e:` and log failures via [`log()`](infrastructure/logger/logger.py) with error level without raising.
  - No GUI framework dependencies (no PySide6, no PyQt, no tkinter).

---

### Task 1.2: [`AllyCore`](brain/reasoning/core.py) Hook Refactoring & Expansion

- **Target File**: [`brain/reasoning/core.py`](brain/reasoning/core.py)
- **Refactoring Existing Hooks**:
  - Replace twelve `Optional[Callable]` attributes in [`AllyCore.__init__`](brain/reasoning/core.py) with [`EventHook`](utils/event_hook.py) instances:
    1. `self.on_pipeline_image = EventHook("on_pipeline_image")`
    2. `self.on_debug_overlay = EventHook("on_debug_overlay")`
    3. `self.on_status_update = EventHook("on_status_update")`
    4. `self.on_state_summary = EventHook("on_state_summary")`
    5. `self.on_prompt_update = EventHook("on_prompt_update")`
    6. `self.on_feedback = EventHook("on_feedback")`
    7. `self.on_chat_message = EventHook("on_chat_message")`
    8. `self.on_eta_ready = EventHook("on_eta_ready")`
    9. `self.on_connection_status = EventHook("on_connection_status")`
    10. `self.on_medium_term = EventHook("on_medium_term")`
    11. `self.on_personality_state = EventHook("on_personality_state")`
    12. `self.on_strategic_memory = EventHook("on_strategic_memory")`
- **Adding Three New Hooks**:
  - `self.on_ocr_result = EventHook("on_ocr_result")`
  - `self.on_scribe_output = EventHook("on_scribe_output")`
  - `self.on_ally_output = EventHook("on_ally_output")`
- **Invocation Updates**:
  - Convert all internal call sites from `if self.on_x is not None: self.on_x(...)` to unconditional `self.on_x.emit(...)`.
  - Remove all obsolete `if self.on_x is not None:` guard checks.
  - Inside [`AllyCore.run_turn()`](brain/reasoning/core.py):
    - Emit [`on_ocr_result`](brain/reasoning/core.py) with payload dataclass/dict: `screen_name`, `confidence`, `is_draft`, `confirmed_facts`, `screen_category`, `skip_scribe_reason`.
    - Emit [`on_scribe_output`](brain/reasoning/core.py) with the raw `ScribeOutput` (or `None` when skipped).
    - Emit [`on_ally_output`](brain/reasoning/core.py) with the complete `AllyOutput` object.

---

### Task 1.3: Call-Site Conversions in [`main.py`](main.py) and [`interfaces/gui/tkinter_app.py`](interfaces/gui/tkinter_app.py)

- **Target Files**:
  - [`main.py`](main.py)
  - [`interfaces/gui/tkinter_app.py`](interfaces/gui/tkinter_app.py)
- **Modifications**:
  - In [`main.py`](main.py) (headless mode wiring):
    - Change `core.on_status_update = ...` to `core.on_status_update.connect(...)`
    - Change `core.on_state_summary = ...` to `core.on_state_summary.connect(...)`
    - Change `core.on_prompt_update = ...` to `core.on_prompt_update.connect(...)`
    - Change `core.on_feedback = ...` to `core.on_feedback.connect(...)`
    - Change `core.on_chat_message = ...` to `core.on_chat_message.connect(...)`
    - Change `core.on_connection_status = ...` to `core.on_connection_status.connect(...)`
  - In [`interfaces/gui/tkinter_app.py`](interfaces/gui/tkinter_app.py) (`AllyOverlay.__init__`):
    - Convert all twelve hook assignments to `.connect()` calls.

---

### Task 1.4: Logger Pub/Sub & [`REGISTRY`](infrastructure/logger/logger.py) Expansion

- **Target File**: [`infrastructure/logger/logger.py`](infrastructure/logger/logger.py)
- **Modifications**:
  - Define `LogEntry` dataclass:

    ```python
    @dataclass
    class LogEntry:
        brain_name: str
        method_name: str
        message: str
        level: str
        timestamp: datetime.datetime
    ```

  - Implement module-level subscriber management:

    ```python
    _subscribers: list[Callable[[LogEntry], None]] = []

    def subscribe(callback: Callable[[LogEntry], None]) -> None:
        if callback not in _subscribers:
            _subscribers.append(callback)

    def unsubscribe(callback: Callable[[LogEntry], None]) -> None:
        if callback in _subscribers:
            _subscribers.remove(callback)
    ```

  - In [`log()`](infrastructure/logger/logger.py), construct a `LogEntry` and dispatch to subscribers in a `try...except` block after existing console/file writing.
  - Expand [`REGISTRY`](infrastructure/logger/logger.py) table to include:

    | Filename | Brain / Subsystem Name | Color Key |
    |---|---|---|
    | `screen_classifier.py` | `ScreenClassifier` | `mint` |
    | `screen_bootstrapper.py` | `ScreenBootstrapper` | `salmon` |
    | `layout_reader.py` | `LayoutOCRReader` | `teal` |
    | `ocr.py` | `OCR` | `olive` |
    | `clip_classifier.py` | `ClipClassifier` | `violet` |
    | `screen_category_store.py` | `CategoryStore` | `lavender` |
    | `entity_registry.py` | `EntityRegistry` | `sky_blue` |
    | `narrative.py` | `NarrativeMemory` | `pink` |
    | `personality.py` | `PersonalityMemory` | `purple` |
    | `save_tracker.py` | `SaveTracker` | `dark_grey` |

---

### Task 1.5: [`TurnTrace`](brain/state/turn_trace.py) Dataclass & Bounded Ring Buffer

- **Target Files**:
  - [`brain/state/turn_trace.py`](brain/state/turn_trace.py)
  - [`brain/reasoning/core.py`](brain/reasoning/core.py)
- **Modifications**:
  - Create [`brain/state/turn_trace.py`](brain/state/turn_trace.py):

    ```python
    from dataclasses import dataclass, field
    from typing import Any

    @dataclass
    class TurnTrace:
        turn: int
        timestamp: float
        screen_name: str
        screen_confidence: float
        is_draft_match: bool
        skip_scribe_reason: str
        skip_ally: bool
        screen_category: str | None
        confirmed_facts: list[Any]
        scribe_output: Any | None
        ally_output: Any | None
        prompt_sent_to_ally: str | None
        timings: dict[str, float] = field(default_factory=dict)
    ```

  - In [`AllyCore.__init__`](brain/reasoning/core.py), initialize `self.turn_traces: deque[TurnTrace] = deque(maxlen=20)`.
  - In [`AllyCore.run_turn()`](brain/reasoning/core.py), time execution of `"scribe"`, `"ally"`, `"entity_resolve"`, and `"memory_record"` with `time.perf_counter()`. Build and append a `TurnTrace` instance at the end of each turn unconditionally.

---

### Task 1.6: Self-Capture Exclusion Subsystem

- **Target Files**:
  - [`interfaces/gui_qt/shell/capture_exclusion.py`](interfaces/gui_qt/shell/capture_exclusion.py)
  - [`brain/state/shell_bounds_registry.py`](brain/state/shell_bounds_registry.py)
  - [`ingestion/collectors/screen_collector.py`](ingestion/collectors/screen_collector.py)
- **Modifications**:
  - **A. OS-Level DWM Exclusion**:
    - Implement `exclude_hwnd_from_capture(hwnd: int) -> bool` in [`interfaces/gui_qt/shell/capture_exclusion.py`](interfaces/gui_qt/shell/capture_exclusion.py) utilizing `ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)`.
  - **B. Software Blackout Masking**:
    - Implement [`ShellBoundsRegistry`](brain/state/shell_bounds_registry.py) with thread-safe `update(shell_id, left, top, width, height)`, `unregister(shell_id)`, and `all_bounds() -> list[tuple[int, int, int, int]]`.
    - Provide module singleton `SHELL_BOUNDS = ShellBoundsRegistry()`.
    - In [`ScreenCollector.capture_bgr()`](ingestion/collectors/screen_collector.py), immediately after frame conversion:
      - Iterate through `SHELL_BOUNDS.all_bounds()`.
      - Translate absolute coordinates to local frame coordinates (`x - self.rect.left`, `y - self.rect.top`).
      - Clip bounding boxes to frame dimensions `[0, width]` and `[0, height]`.
      - If intersection area > 0, apply `cv2.rectangle(frame, (x0, y0), (x1, y1), (0, 0, 0), -1)`.

---

### Task 1.7: Dependency Updates

- **Target File**: [`requirements.txt`](requirements.txt)
- **Modifications**:
  - Add `PySide6` to [`requirements.txt`](requirements.txt).

---

### Task 1.8: Comprehensive Unit Test Suite

- **Target Files**:
  - [`tests/test_event_hook.py`](tests/test_event_hook.py)
  - [`tests/test_turn_trace.py`](tests/test_turn_trace.py)
  - [`tests/test_shell_bounds_registry.py`](tests/test_shell_bounds_registry.py)
  - [`tests/test_logger_pubsub.py`](tests/test_logger_pubsub.py)
- **Test Scenarios**:
  - **`test_event_hook.py`**:
    - Multiple subscribers receive emitted arguments correctly.
    - Disconnected subscribers do not receive events.
    - Exception raised in subscriber 1 does not prevent subscriber 2 from running.
    - Zero-subscriber emission executes without errors.
  - **`test_turn_trace.py`**:
    - Dataclass instantiates with default and explicit fields.
    - Deque ring buffer correctly retains max 20 traces and discards older traces when exceeded.
  - **`test_shell_bounds_registry.py`**:
    - Concurrent thread updates and unregistrations are thread-safe.
    - `all_bounds()` returns correct active rectangles.
  - **`test_logger_pubsub.py`**:
    - Subscribed callbacks receive `LogEntry` instances with accurate attributes.
    - Unsubscribe stops further delivery.
    - Subscriber exceptions do not crash `logger.log()`.

---

## 3. Verification & Acceptance Criteria

1. **Unit Tests**: Run `python tests/run_tests.py` to ensure all existing and new unit tests pass with zero regressions.
2. **Backward Compatibility**: Launch headless mode (`python main.py`) and Tkinter GUI mode (`python main.py --gui`) to confirm hook connections function as expected without errors.
3. **Clean Architecture Compliance**: Zero GUI imports in [`utils/event_hook.py`](utils/event_hook.py), [`brain/reasoning/core.py`](brain/reasoning/core.py), or [`infrastructure/logger/logger.py`](infrastructure/logger/logger.py).
