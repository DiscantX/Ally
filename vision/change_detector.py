"""Superior Colliculus: pre-Scribe change detector for idle safeguarding.

This was added/changed as a part of the ZOO CODE idle safeguard pass.
"""

import time
import cv2
import numpy as np
from logger import log


class ChangeDetector:
    """Performs fast frame-to-frame pixel comparison to detect whether the screen
    has changed significantly enough to warrant processing (Scribe/Ally API calls).
    Acts as the biological 'Superior Colliculus' sensory gate.

    Includes luminance normalization and tuned thresholds to prevent false positives
    from UI hover brightening (e.g. mouse cursor over large buttons or cards),
    along with optional post-trigger cooldown and settling stability checks.

    This was added/changed as a part of the ZOO CODE idle safeguard pass.
    """

    def __init__(
        self,
        threshold_percent: float = 2.0,
        pixel_diff_threshold: int = 30,
        enable_cooldown: bool = False,
        cooldown_seconds: float = 5.0,
        major_change_threshold: float = 20.0,
        enable_stability_check: bool = False,
        stability_threshold_percent: float = 1.0,
    ):
        self.threshold_percent = threshold_percent
        self.pixel_diff_threshold = pixel_diff_threshold
        self._last_frame_gray: np.ndarray | None = None

        # Cooldown mechanism configuration
        self.enable_cooldown = enable_cooldown
        self.cooldown_seconds = cooldown_seconds
        self.major_change_threshold = major_change_threshold
        self._last_trigger_timestamp: float = 0.0

        # Stability / settling check mechanism configuration
        self.enable_stability_check = enable_stability_check
        self.stability_threshold_percent = stability_threshold_percent
        self._in_transition: bool = False

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
        log(f"\nScreen delta: {changed_pixels}/{total_pixels} = {changed_percent}%\n")

        current_time = time.time()

        # 1. Cooldown mechanism (independent toggle)
        if self.enable_cooldown:
            if changed_percent >= self.major_change_threshold:
                if current_time - self._last_trigger_timestamp < self.cooldown_seconds:
                    log(f"[SuperiorColliculus] Cooldown active ({current_time - self._last_trigger_timestamp:.1f}s < {self.cooldown_seconds}s). Skipping trigger.")
                    self._last_frame_gray = gray_normalized
                    return False

        # 2. Stability / settling check mechanism (independent toggle)
        if self.enable_stability_check:
            if changed_percent >= self.threshold_percent:
                if not self._in_transition:
                    self._in_transition = True
                    log("[SuperiorColliculus] Transition started. Waiting for screen to settle.")
                self._last_frame_gray = gray_normalized
                return False
            elif self._in_transition:
                if changed_percent <= self.stability_threshold_percent:
                    self._in_transition = False
                    log(f"[SuperiorColliculus] Screen settled (delta {changed_percent}% <= {self.stability_threshold_percent}%). Triggering turn.")
                    self._last_frame_gray = gray_normalized
                    if self.enable_cooldown:
                        self._last_trigger_timestamp = current_time
                    return True
                else:
                    self._last_frame_gray = gray_normalized
                    return False

        # Standard check (if neither cooldown nor stability check suppresses it)
        if changed_percent >= self.threshold_percent:
            self._last_frame_gray = gray_normalized
            if self.enable_cooldown and changed_percent >= self.major_change_threshold:
                self._last_trigger_timestamp = current_time
            return True

        return False

    def reset(self) -> None:
        """Resets the last frame reference.

        This was added/changed as a part of the ZOO CODE idle safeguard pass.
        """
        self._last_frame_gray = None
        self._in_transition = False
        self._last_trigger_timestamp = 0.0
