"""Generic, data-driven Collector: composes ScreenCollector +
LayoutOCRReader from a small JSON config. This replaces what used to be
a one-off plugin class per game (plugins/slay_the_spire/collector.py).

Adding a new screen-capture-based game now requires zero Python:
1. a config JSON (window title, layout path, source tag)
2. a calibrated layout.json (tools/inspect_coords.py), whenever you get
   around to it -- collection works fine with an uncalibrated/missing
   layout, it just produces no ConfirmedFacts until then.

A real plugin (a bespoke Collector implementation) is still the right
answer for a game that needs something structurally different from
"screenshot + OCR" -- e.g. a CommunicationMod-style internal API that
hands back exact GameState JSON over a socket instead of pixels. That
case gets its own collector_type value (see build_collector below) and
its own class when it's actually needed. Not built -- no game needs it
yet.
"""
import base64
import io
import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from PIL import Image as PILImage

from collectors.base import RawObservation
from collectors.screen_collector import ScreenCollector
from vision.layout_reader import LayoutOCRReader
from vision.screen_classifier import ScreenClassifier
from vision.screen_bootstrapper import ScreenBootstrapper
from logger import log


@dataclass
class CollectorConfig:
    game_id: str
    window_title: str
    layout_dir: str
    source_tag: str
    collector_type: str = "screen_ocr"


def load_collector_config(config_path: str) -> CollectorConfig:
    import json
    data = json.loads(Path(config_path).read_text())
    return CollectorConfig(
        game_id=data["game_id"],
        window_title=data["window_title"],
        layout_dir=data["layout_dir"],
        source_tag=data.get("source_tag", f"ocr:{data['game_id']}"),
        collector_type=data.get("collector_type", "screen_ocr"),
    )


def _decode_anchor(b64_png: str) -> np.ndarray:
    raw = base64.b64decode(b64_png)
    pil = PILImage.open(io.BytesIO(raw)).convert("RGB")
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def build_screen_layouts(layout_dir: str, source_tag_prefix: str) -> tuple[dict[str, LayoutOCRReader], ScreenClassifier]:
    """One layout.json per named screen (combat.json, map.json, ...),
    filename stem = screen name. Missing directory is a logged, non-fatal
    state -- every screen just runs uncalibrated until calibrated."""
    readers: dict[str, LayoutOCRReader] = {}
    classifier = ScreenClassifier()

    if not os.path.isdir(layout_dir):
        log(f"[Collector] No layout directory at {layout_dir} -- Scribe will run in full-UI mode until at least one screen is calibrated.")
        return readers, classifier

    for fname in os.listdir(layout_dir):
        if not fname.endswith(".json"):
            continue
        screen_name = fname[:-5]
        reader = LayoutOCRReader(os.path.join(layout_dir, fname), source_tag=f"{source_tag_prefix}:{screen_name}")
        readers[screen_name] = reader

        for el in reader.layout.elements.values():
            if el.is_anchor and el.anchor_reference:
                classifier.register_anchor(screen_name, el.box, _decode_anchor(el.anchor_reference))

    return readers, classifier


class GenericHudCollector:
    def __init__(self, config: CollectorConfig):
        self.config = config
        self.screen = ScreenCollector(config.window_title)
        self.readers, self.classifier = build_screen_layouts(config.layout_dir, config.source_tag)
        self.bootstrapper = ScreenBootstrapper(config.layout_dir, unknown_streak_threshold=3)
        self._last_frame_bgr = None
        self._last_confirmed_facts: list[ConfirmedFact] = []

        # Union of ignore_motion regions across every known screen -- we
        # don't know which screen we're on until *after* the change
        # detector has already run this frame, so mask globally.
        ignore_regions = [
            el.box
            for reader in self.readers.values()
            for el in reader.layout.elements.values()
            if el.ignore_motion
        ]
        self.screen.change_detector.set_ignore_regions(ignore_regions)

    def capture(self) -> RawObservation:
        frame_bgr = self.screen.capture_bgr()
        if frame_bgr is None:
            return RawObservation(image=None, changed=False)

        self._last_frame_bgr = frame_bgr
        changed = self.screen.change_detector.has_changed(frame_bgr)
        match = self.classifier.classify(frame_bgr)
        bootstrap_ready = self.bootstrapper.note_classification(match.screen_name)
        reader = self.readers.get(match.screen_name)
        confirmed_facts = reader.read(frame_bgr) if reader else []

        # Semantic diff guard: if confirmed facts are identical to last turn,
        # skip Scribe/Ally invocation even if SSIM detected pixel-level motion.
        skip_ally = False
        if (self._last_confirmed_facts and confirmed_facts and
                len(self._last_confirmed_facts) == len(confirmed_facts)):
            facts_match = True
            for last_fact, curr_fact in zip(self._last_confirmed_facts, confirmed_facts):
                if last_fact.key != curr_fact.key or last_fact.value != curr_fact.value:
                    facts_match = False
                    break
            if facts_match:
                skip_ally = True

        # Update last confirmed facts for next comparison
        self._last_confirmed_facts = confirmed_facts.copy()

        image = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        obs = RawObservation(
            image=image, confirmed_facts=confirmed_facts, changed=changed,
            screen_name=match.screen_name, screen_confidence=match.confidence,
            bootstrap_ready=bootstrap_ready,
        )
        # Attach skip_ally flag to observation
        obs.skip_ally = skip_ally
        return obs

    def bootstrap_screen(self, screen_elements: list, screen_name_guess: str):
        """Called from main.py right after Scribe runs, only when capture()
        flagged bootstrap_ready this turn."""
        if self._last_frame_bgr is None:
            log("[Collector] bootstrap_screen called with no cached frame -- skipping.")
            return None
        result = self.bootstrapper.bootstrap(self._last_frame_bgr, screen_elements, screen_name_guess)
        self.readers[result.screen_name] = LayoutOCRReader(
            result.layout_path, source_tag=f"{self.config.source_tag}:{result.screen_name}"
        )
        self.classifier.register_draft_frame(result.screen_name, self._last_frame_bgr)
        return result


def build_collector(config_path: str) -> GenericHudCollector:
    config = load_collector_config(config_path)
    if config.collector_type != "screen_ocr":
        raise NotImplementedError(
            f"collector_type '{config.collector_type}' not implemented -- only "
            f"'screen_ocr' exists today."
        )
    return GenericHudCollector(config)