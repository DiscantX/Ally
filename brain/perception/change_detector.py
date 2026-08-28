"""Superior Colliculus: pre-Scribe change detector for idle safeguarding.

This was added/changed as a part of the ZOO CODE idle safeguard pass.
Extended to add SSIM-based comparison and ROI masking (see set_ignore_regions).
"""

import time
import cv2
import numpy as np
from infrastructure.logger import log
from storage.configs.config_manager import load_user_config

try:
    from skimage.metrics import structural_similarity as ssim
    _SSIM_AVAILABLE = True
except ImportError:
    _SSIM_AVAILABLE = False


class ChangeDetector:
    """Performs frame-to-frame comparison to decide whether the screen has
    changed enough to warrant a Scribe/Ally call. Acts as the 'Superior
    Colliculus' sensory gate.

    Two comparison modes:
    - SSIM (default, if scikit-image is installed): structural similarity,
      much less sensitive to uniform texture/brightness churn (ambient
      background animation) than raw pixel diff, while staying sensitive
      to actual structural change.
    - absdiff (fallback): the original pixel-count-over-threshold method.

    Also supports ROI masking via set_ignore_regions() -- boxes known to
    animate independent of game state (title-screen background, particle
    effects) are zeroed out of both frames before comparison, so they
    can't contribute to the delta at all rather than needing a global
    threshold tuned around them.

    This was added/changed as a part of the ZOO CODE idle safeguard pass.
    """

    def __init__(
        self,
        threshold_percent: float | None = None,
        pixel_diff_threshold: int | None = None,
        enable_cooldown: bool | None = None,
        cooldown_seconds: float | None = None,
        major_change_threshold: float | None = None,
        enable_stability_check: bool | None = None,
        stability_threshold_percent: float | None = None,
        use_ssim: bool | None = None,
        ignore_regions: list[tuple[int, int, int, int]] | None = None,
        gui_app = None,
    ):
        config = load_user_config()
        self.threshold_percent = threshold_percent if threshold_percent is not None else config["threshold_percent"]
        self.pixel_diff_threshold = pixel_diff_threshold if pixel_diff_threshold is not None else config["pixel_diff_threshold"]
        self._last_frame_gray: np.ndarray | None = None
        self.gui_app = gui_app

        self.enable_cooldown = enable_cooldown if enable_cooldown is not None else config["enable_cooldown"]
        self.cooldown_seconds = cooldown_seconds if cooldown_seconds is not None else config["cooldown_seconds"]
        self.major_change_threshold = major_change_threshold if major_change_threshold is not None else config["major_change_threshold"]
        self._last_trigger_timestamp: float = 0.0

        self.enable_stability_check = enable_stability_check if enable_stability_check is not None else config["enable_stability_check"]
        self.stability_threshold_percent = stability_threshold_percent if stability_threshold_percent is not None else config["stability_threshold_percent"]
        self._in_transition: bool = False

        use_ssim_val = use_ssim if use_ssim is not None else config["use_ssim"]
        self.use_ssim = use_ssim_val and _SSIM_AVAILABLE
        if use_ssim_val and not _SSIM_AVAILABLE:
            log(
                "scikit-image not installed -- falling back "
                "to absdiff. `pip install scikit-image` to enable SSIM."
            )

        # (x, y, w, h) boxes zeroed out of every diff. Game-agnostic --
        # ChangeDetector doesn't know what a layout.json is, a Collector
        # just hands it boxes. See set_ignore_regions().
        self.ignore_regions: list[tuple[int, int, int, int]] = ignore_regions or []

    def set_ignore_regions(self, regions: list[tuple[int, int, int, int]]) -> None:
        """Set (x, y, w, h) boxes to mask out of every future comparison.
        Called by a Collector after loading its layout, for any element
        flagged `ignore_motion: true`. Invalidates the current baseline
        frame since the mask itself changed shape."""
        self.ignore_regions = regions or []
        self._last_frame_gray = None

    def _apply_mask(self, gray: np.ndarray) -> np.ndarray:
        if not self.ignore_regions:
            return gray
        masked = gray.copy()
        h, w = masked.shape
        for (x, y, rw, rh) in self.ignore_regions:
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(w, x + rw), min(h, y + rh)
            if x1 > x0 and y1 > y0:
                masked[y0:y1, x0:x1] = 0
        return masked

    def has_changed(self, frame_bgr: np.ndarray) -> bool:
        """Compares current BGR frame against the previous frame with
        luminance normalization and ROI masking. Returns True if changed
        beyond threshold, False if idle.

        This was added/changed as a part of the ZOO CODE idle safeguard pass.
        """
        if frame_bgr is None:
            return False

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if self.gui_app:
            self.gui_app.update_pipeline_image("grayscale", gray, "Grayscale Frame")

        gray = self._apply_mask(gray)
        if self.gui_app:
            self.gui_app.update_pipeline_image("masked_grayscale", gray, "ROI-Masked Grayscale Frame")

        if self._last_frame_gray is None:
            self._last_frame_gray = gray
            if self.gui_app:
                self.gui_app.update_pipeline_image("normalized_grayscale", gray, "Luminance-Normalized Grayscale")
                zero_diff = np.zeros_like(gray)
                self.gui_app.update_pipeline_image("diff", zero_diff, "Absolute Difference Image")
                self.gui_app.update_pipeline_image("thresh", zero_diff, "Thresholded Binary Change Map")
            return True  # First frame is always considered changed

        if gray.shape != self._last_frame_gray.shape:
            self._last_frame_gray = gray
            return True

        # Luminance normalization: neutralize UI hover brightening / global
        # lighting shifts before comparing.
        current_mean = np.mean(gray)
        last_mean = np.mean(self._last_frame_gray)
        mean_diff = current_mean - last_mean
        gray_normalized = np.clip(gray.astype(np.float32) - mean_diff, 0, 255).astype(np.uint8)
        if self.gui_app:
            self.gui_app.update_pipeline_image("normalized_grayscale", gray_normalized, "Luminance-Normalized Grayscale")

        diff = cv2.absdiff(gray_normalized, self._last_frame_gray)
        if self.gui_app:
            self.gui_app.update_pipeline_image("diff", diff, "Absolute Difference Image")
        _, thresh = cv2.threshold(diff, self.pixel_diff_threshold, 255, cv2.THRESH_BINARY)
        if self.gui_app:
            self.gui_app.update_pipeline_image("thresh", thresh, "Thresholded Binary Change Map")

        if self.use_ssim:
            try:
                # Only request full=True if GUI app is actively displaying the diff map
                need_full = self.gui_app is not None
                # Use float32 to avoid float64 memory overhead/fragmentation and specify data_range=255
                img1 = gray_normalized.astype(np.float32)
                img2 = self._last_frame_gray.astype(np.float32)
                result = ssim(img1, img2, full=need_full, data_range=255)
                score = result[0] if isinstance(result, tuple) else result
                changed_percent = max(0.0, (1.0 - float(score))) * 100.0
                if self.gui_app and isinstance(result, tuple) and len(result) > 1:
                    diff_map = np.uint8(np.clip(result[1], 0, 1) * 255)
                    self.gui_app.update_pipeline_image("diff", diff_map, "Absolute Difference Image")
            except (MemoryError, Exception) as e:
                log(f"SSIM calculation failed due to memory/allocation error ({e}), falling back to absdiff.")
                diff = cv2.absdiff(gray_normalized, self._last_frame_gray)
                if self.gui_app:
                    self.gui_app.update_pipeline_image("diff", diff, "Absolute Difference Image")
                _, thresh = cv2.threshold(diff, self.pixel_diff_threshold, 255, cv2.THRESH_BINARY)
                if self.gui_app:
                    self.gui_app.update_pipeline_image("thresh", thresh, "Thresholded Binary Change Map")
                changed_pixels = cv2.countNonZero(thresh)
                total_pixels = gray.shape[0] * gray.shape[1]
                changed_percent = (changed_pixels / total_pixels) * 100.0
        else:
            changed_pixels = cv2.countNonZero(thresh)
            total_pixels = gray.shape[0] * gray.shape[1]
            changed_percent = (changed_pixels / total_pixels) * 100.0

        # log(
        #     f"\nScreen delta: {changed_percent:.3f}% ({'ssim' if self.use_ssim else 'absdiff'})\n"
        # )

        current_time = time.time()

        # 1. Cooldown mechanism (independent toggle)
        if self.enable_cooldown:
            if changed_percent >= self.major_change_threshold:
                if current_time - self._last_trigger_timestamp < self.cooldown_seconds:
                    log(f"Cooldown active ({current_time - self._last_trigger_timestamp:.1f}s < {self.cooldown_seconds}s). Skipping trigger.")
                    self._last_frame_gray = gray_normalized
                    return False

        # 2. Stability / settling check mechanism (independent toggle)
        if self.enable_stability_check:
            if changed_percent >= self.threshold_percent:
                if not self._in_transition:
                    self._in_transition = True
                    log("Transition started. Waiting for screen to settle.")
                self._last_frame_gray = gray_normalized
                return False
            elif self._in_transition:
                if changed_percent <= self.stability_threshold_percent:
                    self._in_transition = False
                    log(f"Screen settled (delta {changed_percent:.3f}% <= {self.stability_threshold_percent}%). Triggering turn.")
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