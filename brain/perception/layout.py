"""Generic JSON-driven layout config: a named set of calibrated pixel
regions (+ OCR hints) for reading a HUD. Nothing game-specific here --
each game plugin supplies its own layout.json path; this class doesn't
care what's in it. Calibrated with tools/inspect_coords.py.
"""

import json
import os
from infrastructure.logger import log, timed


class UIElement:
    def __init__(self, name: str, data: dict) -> None:
        self.name = name
        self.x = data.get("x", 0)
        self.y = data.get("y", 0)
        self.w = data.get("w", 100)
        self.h = data.get("h", 40)
        self.requires_hover = data.get("requires_hover", False)
        self.psm = data.get("psm", 7)
        self.ignore_motion = data.get("ignore_motion", False)
        self.is_anchor = data.get("is_anchor", False)
        self.anchor_reference = data.get("anchor_reference")  # base64 PNG, only if is_anchor
        self.source = data.get("source")          # None once human-edited, else "scribe_auto"
        self.validated = data.get("validated", False)

    @property
    def is_trusted(self) -> bool:
        """Anchors are never OCR-trusted. A human-confirmed box (no
        'source' tag) is always trusted. A scribe_auto draft is trusted
        only if it passed self-confirmation at bootstrap time."""
        if self.is_anchor:
            return False
        if self.source != "scribe_auto":
            return True
        return self.validated

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


class LayoutManager:
    def __init__(self, filepath: str = "layout.json") -> None:
        self.filepath = filepath
        self.elements = {}
        self.load_layouts()

    @timed
    def load_layouts(self) -> None:
        if not os.path.exists(self.filepath):
            log("Warning: {filepath} not found.", filepath=self.filepath)
            return

        with open(self.filepath, "r") as f:
            try:
                raw_data = json.load(f)
                self.elements = {name: UIElement(name, data) for name, data in raw_data.items()}
                log("Loaded {count} UI elements from {filepath}", count=len(self.elements), filepath=self.filepath)
            except json.JSONDecodeError:
                log("Error parsing {filepath}.", filepath=self.filepath)

    def get(self, name: str) -> UIElement | None:
        return self.elements.get(name)
