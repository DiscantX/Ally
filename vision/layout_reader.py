"""Generic layout-driven OCR reader: given a LayoutManager's calibrated
regions and a BGR frame, reads each region with Tesseract and returns
ConfirmedFacts. Reusable as-is by any game -- the only thing a specific
game plugin supplies is the path to its own layout.json (and the window
title, one level up in its Collector).
"""

from collectors.base import ConfirmedFact
from vision.layout import LayoutManager
from vision.ocr import extract_text, preprocess_for_ocr


class LayoutOCRReader:
    def __init__(self, layout_path: str, source_tag: str):
        self.layout = LayoutManager(layout_path)
        self.source_tag = source_tag  # e.g. "ocr:slay_the_spire"

    def read(self, frame_bgr) -> list[ConfirmedFact]:
        facts = []
        for name, element in self.layout.elements.items():
            x, y, w, h = element.box
            crop = frame_bgr[y : y + h, x : x + w]
            processed = preprocess_for_ocr(crop)
            text = extract_text(processed, config=f"--psm {element.psm}")
            if text:
                facts.append(ConfirmedFact(key=name, value=text, source=self.source_tag))
        return facts
