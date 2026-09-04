# Plan: Vision Panel Live Preview & API Processing Responsiveness

## Objective
Implement a QTimer-driven live preview refresh in [`interfaces/gui_qt/dev/panels/vision_panel.py`](interfaces/gui_qt/dev/panels/vision_panel.py:24) to provide real-time visual feedback ("is this thing alive") during Scribe & Ally API network call processing, without altering the throttled, sequential main capture/OCR pipeline [`main.py`](main.py:1).

---

## Architectural Analysis & Decisions
1. **Root Cause**: [`main.py`](main.py:1) runs [`AllyCore.run_loop()`](brain/reasoning/core.py:1) sequentially: `capture()` -> `run_turn()` (blocking on network calls to Scribe/Ally) -> `sleep`. Pipeline images are emitted inside `capture()`, so while waiting on network calls, no new frames are captured or emitted.
2. **Throttle Decision**: Keep the main capture/OCR throttle as-is. It provides a valuable, accidental pacing benefit (at most one API call in flight at a time).
3. **Decoupled Live Preview**: Add a separate `"live_preview"` slot in [`interfaces/gui_qt/dev/panels/vision_panel.py`](interfaces/gui_qt/dev/panels/vision_panel.py:68) driven by a local `QTimer` (~750ms interval).
4. **Stateless Grab**: Use stateless `ScreenCollector.capture_bgr()` (mss grab + BGR conversion) to avoid thread safety risks in `ChangeDetector` or `ScreenClassifier`.
5. **Tradeoff Note**: Window position/size (`ClientRect`) updates on the main loop thread while read concurrently by the Qt timer thread—a minor cosmetic-only race resulting in at most one slightly miscropped preview frame per tick, acceptable for a debug preview.

---

## Actionable Steps

### 1. Update [`interfaces/gui_qt/dev/panels/vision_panel.py`](interfaces/gui_qt/dev/panels/vision_panel.py:24) Pipeline Definitions & Slots
- Add `"live_preview"` slot (e.g., titled `"Live Preview (Unthrottled)"`) to `pipeline_defs` in [`interfaces/gui_qt/dev/panels/vision_panel.py`](interfaces/gui_qt/dev/panels/vision_panel.py:68).
- Ensure the live preview card is visually distinct or positioned appropriately in the vision panel.

### 2. Implement QTimer & Polling Logic in [`interfaces/gui_qt/dev/panels/vision_panel.py`](interfaces/gui_qt/dev/panels/vision_panel.py:24)
- Add a `QTimer` initialized in `VisionPanel.__init__()` with a conservative ~750ms interval.
- Connect timer timeout to a new `_poll_live_preview()` method.
- Retrieve the active `ScreenCollector` reference (or access via dev window bridge / core controller).
- Call `screen_collector.capture_bgr()` safely (handling uninitialized or minimized window states without crashing).
- Feed the resulting BGR numpy frame into `handle_pipeline_image("live_preview", bgr_frame, "Live Preview")`.

### 3. Handle Lifecycle & Cleanup
- Stop the `QTimer` when `VisionPanel` closes or hides.
- Ensure graceful handling if collector or window handle is unavailable.

### 4. Testing & Verification
- Verify that the live preview updates smoothly even when Scribe & Ally API calls are actively processing.
- Verify that the official `"observation"` slot continues to reflect only the frame actually reasoned about that turn.
