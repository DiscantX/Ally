"""Identifies which named UI screen (combat, map, shop...) the current
frame is showing, using cheap local image comparison against calibrated
anchor crops -- no API call, no Scribe involvement.

An anchor is a stable, visually distinctive box within a screen's
layout, flagged is_anchor=True and calibrated the same way as any other
box (inspect_coords.py's 'A' toggle). At runtime we crop the current
frame at that box's coordinates and compare it (SSIM) against the
reference crop captured at calibration time. Highest-scoring screen
above threshold wins; nothing above threshold -> "unknown".

Runs before Scribe every turn -- this is what lets the pipeline pick the
right OCR layout and the right Scribe prompt (UI vs NO_UI) without an
extra API call and without a one-turn classification lag.
"""

from dataclasses import dataclass

import cv2
import numpy as np

try:
    from skimage.metrics import structural_similarity as ssim
    _SSIM_AVAILABLE = True
except ImportError:
    _SSIM_AVAILABLE = False


@dataclass
class ScreenMatch:
    screen_name: str
    confidence: float  # 0.0-1.0, best anchor similarity score


class ScreenClassifier:
    def __init__(self, match_threshold: float = 0.85):
        self.match_threshold = match_threshold
        self._anchors: dict[str, tuple[tuple[int, int, int, int], np.ndarray]] = {}

    def register_anchor(self, screen_name: str, box: tuple[int, int, int, int], reference_bgr: np.ndarray) -> None:
        gray = cv2.cvtColor(reference_bgr, cv2.COLOR_BGR2GRAY)
        self._anchors[screen_name] = (box, gray)

    def classify(self, frame_bgr: np.ndarray) -> ScreenMatch:
        if not self._anchors:
            return ScreenMatch("unknown", 0.0)

        gray_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        best_name, best_score = "unknown", 0.0

        for name, (box, reference_gray) in self._anchors.items():
            x, y, w, h = box
            crop = gray_frame[y:y + h, x:x + w]
            if crop.shape != reference_gray.shape:
                continue  # window resized or bad calibration -- skip, don't crash
            score = self._similarity(crop, reference_gray)
            if score > best_score:
                best_name, best_score = name, score

        if best_score < self.match_threshold:
            return ScreenMatch("unknown", best_score)
        return ScreenMatch(best_name, best_score)

    def _similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        if _SSIM_AVAILABLE:
            score = ssim(a, b, full=False)
            val = score[0] if isinstance(score, tuple) else score
            return max(0.0, float(val))
        hist_a = cv2.calcHist([a], [0], None, [256], [0, 256])
        hist_b = cv2.calcHist([b], [0], None, [256], [0, 256])
        cv2.normalize(hist_a, hist_a)
        cv2.normalize(hist_b, hist_b)
        return max(0.0, cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL))