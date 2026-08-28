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

draft_match_threshold note: whole-frame SSIM draft matching (used for
auto-bootstrapped screens, before any anchor has been manually
calibrated) is coarser than anchor matching -- it's comparing an entire
downscaled frame, not one hand-picked distinctive region, so two
screens that share most of their layout but differ in one meaningful
way (e.g. a ship-selection screen vs. the gameplay screen showing the
same ship) can score deceptively high similarity and get merged. Bumped
from the original 0.85 to 0.93 after exactly that happened in practice
(FTL's ship-select and in-flight screens were classified as the same
screen). This is still a coarse, un-tuned guess, not a measured value --
per ally_decision_log.md's existing "SSIM thresholds ... need to be
re-measured against real capture sessions" flag, this remains open. The
more reliable real fix for a specific pair of screens that keeps
conflating is a manually calibrated anchor (inspect_coords.py's 'A'
toggle) on a small region that's reliably different between them --
anchor matching is deliberately more precise than the draft fallback.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from storage.configs.config_manager import load_user_config

try:
    from skimage.metrics import structural_similarity as ssim
    _SSIM_AVAILABLE = True
except ImportError:
    _SSIM_AVAILABLE = False

@dataclass
class ScreenMatch:
    screen_name: str
    confidence: float
    is_draft: bool = False  # matched via whole-frame draft signature, not a real anchor


class ScreenClassifier:
    def __init__(self, match_threshold: float | None = None, draft_match_threshold: float | None = None, draft_frame_size: tuple[int, int] = (160, 90), gui_app = None):
        config = load_user_config()
        self.match_threshold = match_threshold if match_threshold is not None else config["match_threshold"]
        self.draft_match_threshold = draft_match_threshold if draft_match_threshold is not None else config["draft_match_threshold"]
        self.draft_frame_size = draft_frame_size
        self._anchors: dict[str, tuple[tuple[int, int, int, int], np.ndarray]] = {}
        self._draft_frames: dict[str, np.ndarray] = {}
        self.gui_app = gui_app

    def register_anchor(self, screen_name: str, box: tuple[int, int, int, int], reference_bgr: np.ndarray) -> None:
        gray = cv2.cvtColor(reference_bgr, cv2.COLOR_BGR2GRAY)
        self._anchors[screen_name] = (box, gray)

    def register_draft_frame(self, screen_name: str, frame_bgr: np.ndarray) -> None:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        self._draft_frames[screen_name] = cv2.resize(gray, self.draft_frame_size, interpolation=cv2.INTER_AREA)

    def classify(self, frame_bgr: np.ndarray) -> ScreenMatch:
        gray_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if self.gui_app:
            self.gui_app.update_pipeline_image("classifier_gray", gray_frame, "Classifier Grayscale Frame")

        if self._anchors:
            best_name, best_score = "unknown", 0.0
            for name, (box, reference_gray) in self._anchors.items():
                x, y, w, h = box
                crop = gray_frame[y:y + h, x:x + w]
                if self.gui_app:
                    self.gui_app.update_pipeline_image("classifier_crop", crop, "Anchor Crop / Draft Frame")
                if crop.shape != reference_gray.shape:
                    continue
                score = self._similarity(crop, reference_gray)
                if score > best_score:
                    best_name, best_score = name, score
            if best_score >= self.match_threshold:
                return ScreenMatch(best_name, best_score)

        if self._draft_frames:
            small = cv2.resize(gray_frame, self.draft_frame_size, interpolation=cv2.INTER_AREA)
            if self.gui_app:
                self.gui_app.update_pipeline_image("classifier_crop", small, "Anchor Crop / Draft Frame")
            best_name, best_score = "unknown", 0.0
            for name, ref in self._draft_frames.items():
                score = self._similarity(small, ref)
                if score > best_score:
                    best_name, best_score = name, score
            if best_score >= self.draft_match_threshold:
                return ScreenMatch(best_name, best_score, is_draft=True)

        return ScreenMatch("unknown", 0.0)

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