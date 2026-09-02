"""Screen Bootstrapper: closes the loop on unrecognized screens with zero
human intervention (see ally_decision_log.md — Ally does the work).

When ScreenClassifier reports 'unknown' for several turns running, this
drafts a new screen entirely from data already produced that turn:
  - name: Scribe's own screen_name_guess, sanitized
  - candidate boxes: Scribe's screen_elements (already returned, since an
    unknown screen already runs Scribe in full UI mode)
  - classification signature: whole-frame SSIM (anchor auto-selection
    deferred, see decision log)
  - trust: each box is OCR'd immediately and self-confirmed via
    vision.ocr.looks_like_real_text -- no human review step
"""

import json
import os
import re
import time
from dataclasses import dataclass
from cabinet.configs.config_manager import load_user_config

import numpy as np

from brain.perception.geometry import normalized_box_to_pixels
from brain.perception.ocr import extract_text, preprocess_for_ocr, looks_like_real_text
from infrastructure.logger import log, timed


def _sanitize(raw: str, fallback: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_") or fallback


@dataclass
class BootstrapResult:
    screen_name: str
    layout_path: str
    elements_drafted: int
    elements_validated: int


class ScreenBootstrapper:
    _first_setup_done = False

    @timed
    def __init__(self, layout_dir: str, unknown_streak_threshold: int | None = None) -> None:
        start_t = time.perf_counter()
        config = load_user_config()
        self.layout_dir = layout_dir
        self.unknown_streak_threshold = unknown_streak_threshold if unknown_streak_threshold is not None else config["unknown_streak_threshold"]
        self._unknown_streak = 0
        self._drafted_names: set[str] = set()
        duration = time.perf_counter() - start_t
        if not ScreenBootstrapper._first_setup_done:
            ScreenBootstrapper._first_setup_done = True
            log("Initialized screen collector bootstrapper in {duration:.4f}s", duration=duration)

    def note_classification(self, screen_name: str) -> bool:
        """Call once per turn with this turn's classification. Returns
        True once eligible to bootstrap (consecutive-unknown streak past
        threshold) -- a single ambiguous frame shouldn't fire this."""
        self._unknown_streak = self._unknown_streak + 1 if screen_name == "unknown" else 0
        return self._unknown_streak >= self.unknown_streak_threshold

    def reset(self) -> None:
        self._unknown_streak = 0

    @timed
    def bootstrap(self, frame_bgr: np.ndarray, screen_elements: list, screen_name_guess: str) -> BootstrapResult:
        h, w = frame_bgr.shape[:2]
        base = _sanitize(screen_name_guess, "unknown_screen")
        screen_name, suffix = base, 1
        while screen_name in self._drafted_names:
            suffix += 1
            screen_name = f"{base}_{suffix}"
        self._drafted_names.add(screen_name)

        layout, validated_count = {}, 0
        for el in screen_elements:
            x, y, bw, bh = normalized_box_to_pixels(el.box_2d, w, h)
            crop = frame_bgr[y:y + bh, x:x + bw]
            text = extract_text(preprocess_for_ocr(crop), config="--psm 7")
            validated = looks_like_real_text(text)
            validated_count += validated

            key = _sanitize(el.label, el.id)
            layout[key] = {
                "x": x, "y": y, "w": bw, "h": bh,
                "requires_hover": False, "ignore_motion": False, "psm": 7,
                "source": "scribe_auto", "validated": validated,
            }

        os.makedirs(self.layout_dir, exist_ok=True)
        layout_path = os.path.join(self.layout_dir, f"{screen_name}.json")
        with open(layout_path, "w") as f:
            json.dump(layout, f, indent=4)

        log(
            "Drafted screen '{screen_name}' ({n} elements, {v} self-confirmed) "
            "at {path} -- no human step required.",
            screen_name=screen_name, n=len(layout), v=validated_count, path=layout_path,
        )
        self.reset()
        return BootstrapResult(screen_name, layout_path, len(layout), validated_count)