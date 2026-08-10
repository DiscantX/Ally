# Plan: Idle Safeguard (Superior Colliculus Change Detector)

This was added/changed as a part of the ZOO CODE idle safeguard pass.

## Overview

Implement a fast, low-cost pre-Scribe image comparison pass (the **Superior Colliculus** brain analogue identified in `docs/ally_decision_log.md`) to prevent unnecessary API requests and perception/reasoning runs when the user is idle.

## Design Details

### 1. The Superior Colliculus Module (`vision/change_detector.py`)

- **Purpose**: Compare the current screen frame with the previously processed frame using fast OpenCV/NumPy operations.
- **Algorithm**:
  1. Convert frames to grayscale (or work in BGR).
  2. Compute absolute difference between current frame and previous frame (`cv2.absdiff`).
  3. Apply a small pixel intensity delta threshold (`cv2.threshold`) to filter out minor noise and subtle micro-animations/pulsing.
  4. Calculate the percentage of changed pixels exceeding the threshold.
  5. Compare against a configurable `change_threshold_percent` (e.g., `0.5%` or `1.0%`).
  6. If change is below threshold, return `is_changed = False`, skipping the Scribe and Ally API calls for this tick.
- **Handling Mouse Movement**:
  - Small cursor movements change very few pixels (typically < 0.1% of a game window). A threshold of `0.5%` or `1.0%` effectively ignores cursor movement.
- **Handling Animated Elements**:
  - Subtle pulsing health bars or idle animations affect local pixel intensities slightly. The pixel intensity threshold (e.g. delta > 15-20 out of 255) ignores minor color fluctuations while capturing real state transitions (menus opening, text changing, screens loading).
- **Execution Time**:
  - < 5 milliseconds per frame using vectorized NumPy/OpenCV operations.

### 2. Integration Point

- Integrate into `ScreenCollector` or `SlayTheSpireCollector` (or as an optional guard in `ScreenCollector.capture()` / `main.py`).
- When `is_changed` is False:
  - Log an idle message (`[SuperiorColliculus] Screen unchanged (idle). Skipping API call.`).
  - Return an observation indicating no change or skip turn processing.

### 3. Required Comment Tag

Every modified or newly created file/code block will include:
`# This was added/changed as a part of the ZOO CODE idle safeguard pass`
