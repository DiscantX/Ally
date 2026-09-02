"""Generic screen-capture Collector.

Ported from the NeowsEye prototype (window_manager.py / capture.py /
client.py), reshaped to satisfy the Collector protocol: give it a window
title, it hands back a RawObservation with a PIL image the Scribe can
consume directly. No OCR, no layout knowledge -- that's a per-game
plugin's job (see plugins/slay_the_spire/collector.py), which composes
with this class rather than subclassing it.

This is intentionally the only place that knows about win32/mss, so a
future non-Windows capture backend is a one-file swap.
"""

import time
import cv2
import mss
import numpy as np
from PIL import Image

from ingestion.collectors.base import RawObservation
from ingestion.collectors.window_manager import ClientRect
from brain.perception.change_detector import ChangeDetector  # This was added/changed as a part of the ZOO CODE idle safeguard pass
from brain.state.shell_bounds_registry import SHELL_BOUNDS
from cabinet.configs.config_manager import load_user_config
from infrastructure.logger import log, timed


class ScreenCollector:
    _first_capture_done = False

    def __init__(self, window_title: str, always_on_top: bool = True) -> None:
        self.window_title = window_title
        self.rect = ClientRect(window_title)
        self._always_on_top = always_on_top
        self._prepared = False
        self.change_detector = ChangeDetector(
            enable_stability_check=True,
            enable_cooldown=True,
        )  # This was added/changed as a part of the ZOO CODE idle safeguard pass

    def prepare_window(self) -> None:
        """Snap/focus/pin the window. Call once at startup; capture()
        will also call this lazily on first use."""
        if not self.rect.handle:
            return
        self.rect.move_to_top_left()
        self.rect.bring_to_foreground()
        if self._always_on_top:
            self.rect.set_always_on_top(True)
        self._prepared = True

    def _downscale_image(self, image: Image.Image) -> Image.Image:
        try:
            config = load_user_config()
            if not config.get("enable_downscaling", True):
                return image
            max_size = int(config.get("downscale_max_size", 950))
            w, h = image.size
            if max(w, h) > max_size:
                if w > h:
                    new_w = max_size
                    new_h = int(h * (max_size / w))
                else:
                    new_h = max_size
                    new_w = int(w * (max_size / h))
                return image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        except Exception as e:
            log("Failed to downscale image: {error}", error=str(e), level="warning")
        return image

    @timed
    def capture(self) -> RawObservation:
        start_t = time.perf_counter()
        if not self._prepared:
            self.prepare_window()
        frame = self.capture_bgr()
        if frame is None:
            return RawObservation(image=None, changed=False)
        changed = self.change_detector.has_changed(frame)  # This was added/changed as a part of the ZOO CODE idle safeguard pass
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image = self._downscale_image(image)
        duration = time.perf_counter() - start_t
        if not ScreenCollector._first_capture_done:
            ScreenCollector._first_capture_done = True
            log("Completed first screen capture in {duration:.4f}s", duration=duration)
        return RawObservation(image=image, changed=changed)

    @timed
    def capture_bgr(self) -> np.ndarray | None:
        """Raw BGR numpy frame. Exposed separately (not just via capture())
        so OpenCV-based readers -- e.g. a plugin's HUD OCR -- can reuse the
        same grab without going through PIL and back."""
        if not self.rect.handle or self.rect.width <= 0 or self.rect.height <= 0:
            log("'{window_title}' not found or minimized.", window_title=self.window_title)
            return None

        monitor = {
            "left": self.rect.left,
            "top": self.rect.top,
            "width": self.rect.width,
            "height": self.rect.height,
        }
        with mss.mss() as sct:
            sct_img = sct.grab(monitor)
            frame = np.array(sct_img)
            bgr_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            frame_h, frame_w = bgr_frame.shape[:2]
            for (bx, by, bw, bh) in SHELL_BOUNDS.all_bounds():
                x0 = max(0, bx - self.rect.left)
                y0 = max(0, by - self.rect.top)
                x1 = min(frame_w, bx - self.rect.left + bw)
                y1 = min(frame_h, by - self.rect.top + bh)
                if x0 < x1 and y0 < y1:
                    cv2.rectangle(bgr_frame, (x0, y0), (x1, y1), (0, 0, 0), -1)
            
            return bgr_frame
