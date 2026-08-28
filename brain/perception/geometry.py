"""Shared coordinate conversion between the two bounding-box formats in
use across the pipeline:

- Scribe (schema.ScreenElement.box_2d): [y_min, x_min, y_max, x_max],
  normalized 0-1000, relative to the full frame. Gemini's native format.
- Calibrated layout (vision.layout.UIElement / layout.json): x, y, w, h
  in absolute pixels, relative to the captured window's client area.
  This is what Tesseract needs -- an exact pixel crop.

Nothing upstream should silently assume one format means the other;
every call site converts explicitly through here.
"""

from infrastructure.logger import log


def normalized_box_to_pixels(box_2d: list[int], frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
    """Scribe's [y_min, x_min, y_max, x_max] (0-1000) -> (x, y, w, h) pixels."""
    if not isinstance(box_2d, (list, tuple)) or len(box_2d) != 4:
        log("Warning: Invalid box_2d received: {box}, expected 4 coordinates. Defaulting to [0, 0, 0, 0].", box=box_2d)
        y_min, x_min, y_max, x_max = 0, 0, 0, 0
    else:
        y_min, x_min, y_max, x_max = box_2d
    x = round((x_min / 1000) * frame_w)
    y = round((y_min / 1000) * frame_h)
    w = round(((x_max - x_min) / 1000) * frame_w)
    h = round(((y_max - y_min) / 1000) * frame_h)
    return x, y, w, h


def pixels_to_normalized_box(x: int, y: int, w: int, h: int, frame_w: int, frame_h: int) -> list[int]:
    """(x, y, w, h) pixels -> Scribe-style [y_min, x_min, y_max, x_max] (0-1000)."""
    x_min = round((x / frame_w) * 1000)
    y_min = round((y / frame_h) * 1000)
    x_max = round(((x + w) / frame_w) * 1000)
    y_max = round(((y + h) / frame_h) * 1000)
    return [y_min, x_min, y_max, x_max]