"""Shared box-overlay drawing for OCR/layout debugging.

Used by the live debug window (wired from main.py's run_turn) to show
exactly which pixel regions the current screen's LayoutOCRReader is
reading, and what text it extracted from each -- so box misalignment or
bad OCR reads can be diagnosed by eye during actual play, not only
through tools/inspect_coords.py's separate calibration UI.

Same color convention as inspect_coords.py's redraw_canvas: green =
calibrated & trusted, orange = an unconfirmed scribe_auto draft, blue =
an anchor (never OCR'd, used only for screen classification). Not a
replacement for inspect_coords.py -- that's still the tool for actually
moving/creating/deleting boxes. This is read-only visualization of
what's already calibrated, layered onto the same frame Ally is looking
at this turn.
"""

import cv2
import numpy as np

from ingestion.collectors.base import ConfirmedFact
from brain.perception.layout import LayoutManager

TRUSTED_COLOR = (0, 255, 0)      # green -- calibrated & trusted for OCR
UNTRUSTED_COLOR = (0, 165, 255)  # orange -- scribe_auto draft, not yet self-confirmed
ANCHOR_COLOR = (255, 0, 0)       # blue -- is_anchor, never OCR'd


def draw_layout_overlay(
    frame_bgr: np.ndarray,
    layout: LayoutManager | None,
    confirmed_facts: list[ConfirmedFact] | None = None,
) -> np.ndarray:
    """Returns a copy of frame_bgr with every calibrated box for `layout`
    drawn on top, labeled with its name and (if available) the OCR value
    just read from it this turn. `layout` may be None (e.g. an
    unrecognized/uncalibrated screen) -- returns the frame untouched, so
    callers don't need to special-case a missing reader."""
    if layout is None or not layout.elements:
        return frame_bgr

    overlay = frame_bgr.copy()
    facts_by_key = {f.key: f.value for f in (confirmed_facts or [])}

    for name, element in layout.elements.items():
        x, y, w, h = element.box
        if element.is_anchor:
            color = ANCHOR_COLOR
        elif element.is_trusted:
            color = TRUSTED_COLOR
        else:
            color = UNTRUSTED_COLOR

        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 1)

        value = facts_by_key.get(name)
        label = f"{name}: '{value}'" if value else name
        cv2.putText(
            overlay, label, (x, max(10, y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA,
        )

    return overlay