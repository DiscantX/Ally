"""Generic OCR primitives, ported unchanged from the NeowsEye prototype's
vision.py. Nothing here knows about Slay the Spire or any other game --
crop a region, clean it up for Tesseract, run Tesseract. Reused by
vision/layout_reader.py and by tools/inspect_coords.py's live preview.
"""

import cv2
import numpy as np
import pytesseract


def crop_region(frame: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """Crops a specific sub-rectangle from a frame.

    box format: (x, y, width, height)
    """
    x, y, w, h = box
    return frame[y : y + h, x : x + w]


def preprocess_for_ocr(crop: np.ndarray | None) -> np.ndarray | None:
    """Converts a cropped image to high-contrast black-and-white,
    optimized for Tesseract OCR."""
    if crop is None or crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def extract_text(processed_image: np.ndarray | None, config: str = "--psm 7") -> str:
    """Runs Tesseract OCR on a preprocessed image patch."""
    if processed_image is None:
        return ""
    return pytesseract.image_to_string(processed_image, config=config).strip()
    
def looks_like_real_text(text: str, min_alnum_ratio: float = 0.5) -> bool:
    """Coarse self-confirmation check: is this OCR output probably real
    text, not garbage? Lets a bootstrapped screen validate its own draft
    boxes with no human review. Deliberately simple (character-class
    ratio, not a dictionary or language-model check) -- flagged to revisit
    if noisy OCR starts leaking into ConfirmedFacts undetected."""
    cleaned = text.strip()
    if not cleaned:
        return False
    alnum = sum(c.isalnum() for c in cleaned)
    return alnum / len(cleaned) >= min_alnum_ratio
