"""Generic OCR primitives, ported unchanged from the NeowsEye prototype's
vision.py. Nothing here knows about Slay the Spire or any other game --
crop a region, clean it up for Tesseract, run Tesseract. Reused by
vision/layout_reader.py and by tools/inspect_coords.py's live preview.
"""

import cv2
import pytesseract


def crop_region(frame, box):
    """Crops a specific sub-rectangle from a frame.

    box format: (x, y, width, height)
    """
    x, y, w, h = box
    return frame[y : y + h, x : x + w]


def preprocess_for_ocr(crop):
    """Converts a cropped image to high-contrast black-and-white,
    optimized for Tesseract OCR."""
    if crop is None or crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def extract_text(processed_image, config="--psm 7"):
    """Runs Tesseract OCR on a preprocessed image patch."""
    if processed_image is None:
        return ""
    return pytesseract.image_to_string(processed_image, config=config).strip()
