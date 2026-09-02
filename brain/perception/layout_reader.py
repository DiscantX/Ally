"""Generic layout-driven OCR reader: given a LayoutManager's calibrated
regions and a BGR frame, reads each region with Tesseract and returns
ConfirmedFacts. Reusable as-is by any game -- the only thing a specific
game plugin supplies is the path to its own layout.json (and the window
title, one level up in its Collector).
"""

from ingestion.collectors.base import ConfirmedFact
from brain.perception.layout import LayoutManager
from brain.perception.ocr import extract_text, preprocess_for_ocr


class LayoutOCRReader:
    def __init__(self, layout_path: str, source_tag: str) -> None:
        self.layout = LayoutManager(layout_path)
        self.source_tag = source_tag

    @property
    def has_calibrated_fields(self) -> bool:
        """True once at least one non-anchor element has been calibrated.
        is_anchor elements exist only so ScreenClassifier can recognize
        the screen -- they were never meant to be OCR'd as HUD values,
        so they don't count toward "this screen's OCR is ready."""
        return any(el.is_trusted for el in self.layout.elements.values())

    def read(self, frame_bgr: Any) -> list[ConfirmedFact]:
        facts = []
        for name, element in self.layout.elements.items():
            if not element.is_trusted:
                continue
            x, y, w, h = element.box
            crop = frame_bgr[y : y + h, x : x + w]
            processed = preprocess_for_ocr(crop)
            text = extract_text(processed, config=f"--psm {element.psm}")
            if text:
                facts.append(ConfirmedFact(key=name, value=text, source=self.source_tag))
        return facts
