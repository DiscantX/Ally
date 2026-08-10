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

import cv2
import mss
import numpy as np
from PIL import Image

from collectors.base import RawObservation
from collectors.window_manager import ClientRect


class ScreenCollector:
    def __init__(self, window_title: str, always_on_top: bool = True):
        self.window_title = window_title
        self.rect = ClientRect(window_title)
        self._always_on_top = always_on_top
        self._prepared = False

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

    def capture(self) -> RawObservation:
        if not self._prepared:
            self.prepare_window()
        frame = self.capture_bgr()
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) if frame is not None else None
        return RawObservation(image=image)

    def capture_bgr(self) -> np.ndarray | None:
        """Raw BGR numpy frame. Exposed separately (not just via capture())
        so OpenCV-based readers -- e.g. a plugin's HUD OCR -- can reuse the
        same grab without going through PIL and back."""
        if not self.rect.handle or self.rect.width <= 0 or self.rect.height <= 0:
            print(f"[ScreenCollector] '{self.window_title}' not found or minimized.")
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
            return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
