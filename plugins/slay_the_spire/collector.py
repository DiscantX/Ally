"""Slay the Spire Collector: composes the *generic* ScreenCollector and
LayoutOCRReader (both in collectors/ and vision/, reused by any game)
with this game's own window title and calibrated layout.json. This file
is the entire STS-specific footprint of the OCR path -- everything else
is shared. This is the concrete shape a plugin takes per the decision
log: it supplies collection/parsing, never reasoning. Ally and the
Scribe are never imported here.
"""

import os

import cv2
from PIL import Image

from collectors.base import RawObservation
from collectors.screen_collector import ScreenCollector
from vision.layout_reader import LayoutOCRReader

LAYOUT_PATH = os.path.join(os.path.dirname(__file__), "layout.json")


class SlayTheSpireCollector:
    def __init__(self):
        self.screen = ScreenCollector("Slay the Spire")
        self.hud = LayoutOCRReader(LAYOUT_PATH, source_tag="ocr:slay_the_spire")

    def capture(self) -> RawObservation:
        # Single grab, reused for both the Scribe's image and the HUD OCR
        # pass, rather than calling ScreenCollector.capture() and
        # capture_bgr() separately (which would grab twice).
        frame_bgr = self.screen.capture_bgr()
        if frame_bgr is None:
            return RawObservation(image=None, changed=False)

        changed = self.screen.change_detector.has_changed(frame_bgr)  # This was added/changed as a part of the ZOO CODE idle safeguard pass
        image = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        confirmed_facts = self.hud.read(frame_bgr)
        return RawObservation(image=image, confirmed_facts=confirmed_facts, changed=changed)
