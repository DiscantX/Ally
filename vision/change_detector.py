"""Superior Colliculus: pre-Scribe change detector for idle safeguarding.

This was added/changed as a part of the ZOO CODE idle safeguard pass.
"""

import cv2
import numpy as np


class ChangeDetector:
    """Performs fast frame-to-frame pixel comparison to detect whether the screen
    has changed significantly enough to warrant processing (Scribe/Ally API calls).
    Acts as the biological 'Superior Colliculus' sensory gate.

    Includes luminance normalization and tuned thresholds to prevent false positives
    from UI hover brightening (e.g. mouse cursor over large buttons or cards).

    This was added/changed as a part of the ZOO CODE idle safeguard pass.
    """

    def __init__(self, threshold_percent: float = 2.0, pixel_diff_threshold: int = 30):
        self.threshold_percent = threshold_percent
        self.pixel_diff_threshold = pixel_diff_threshold
        self._last_frame_gray: np.ndarray | None = None

    def has_changed(self, frame_bgr: np.ndarray) -> bool:
        """Compares current BGR frame against the previous frame with luminance
        normalization to ignore uniform hover brightening.
        Returns True if changed beyond threshold, False if idle.

        This was added/changed as a part of the ZOO CODE idle safeguard pass.
        """
        if frame_bgr is None:
            return False

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        if self._last_frame_gray is None:
            self._last_frame_gray = gray
            return True  # First frame is always considered changed

        # Ensure dimensions match (in case window resized)
        if gray.shape != self._last_frame_gray.shape:
            self._last_frame_gray = gray
            return True

        # Luminance normalization: adjust current frame mean brightness to match last frame
        # to neutralize UI hover brightening / global lighting shifts.
        current_mean = np.mean(gray)
        last_mean = np.mean(self._last_frame_gray)
        mean_diff = current_mean - last_mean

        # Shift gray by mean diff (clipped to uint8 range)
        gray_normalized = np.clip(gray.astype(np.float32) - mean_diff, 0, 255).astype(np.uint8)

        # Absolute difference
        diff = cv2.absdiff(gray_normalized, self._last_frame_gray)

        # Threshold to ignore minor noise and subtle micro-animations / hover highlights
        _, thresh = cv2.threshold(diff, self.pixel_diff_threshold, 255, cv2.THRESH_BINARY)

        # Count changed pixels
        changed_pixels = cv2.countNonZero(thresh)
        total_pixels = gray.shape[0] * gray.shape[1]
        changed_percent = (changed_pixels / total_pixels) * 100.0
        print(f"\n\033[36m[SuperiorColliculus]\033[0m Screen delta: {changed_pixels}/{total_pixels} = {changed_percent}%\n")

        if changed_percent >= self.threshold_percent:
            self._last_frame_gray = gray_normalized
            return True

        return False

    def reset(self) -> None:
        """Resets the last frame reference.

        This was added/changed as a part of the ZOO CODE idle safeguard pass.
        """
        self._last_frame_gray = None
