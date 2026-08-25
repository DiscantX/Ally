"""Collector interface: the pluggable "how do we get game state" layer.

Every Collector, however it gets its data (screen capture, an internal
API like CommunicationMod, player text), produces a RawObservation: an
image for the Scribe to look at, plus zero or more ConfirmedFacts the
Scribe never needs to touch because they were read with certainty (e.g.
exact HP via OCR against a known-good layout, or a modding API).

ConfirmedFacts skip the vision LLM call entirely -- they go straight into
the Sandbox, tagged with their source, so Ally can treat them as ground
truth rather than an interpretation. This is the concrete implementation
of the design doc's "Internal APIs" collection avenue, generalized to
also cover calibrated OCR.
"""

from dataclasses import dataclass, field
from typing import Protocol

from PIL import Image


@dataclass
class ConfirmedFact:
    key: str  # e.g. "player_hp", "gold"
    value: str
    source: str  # e.g. "ocr:slay_the_spire", "communication_mod"


@dataclass
class RawObservation:
    image: Image.Image | None
    confirmed_facts: list[ConfirmedFact] = field(default_factory=list)
    changed: bool = True
    screen_name: str = "unknown"
    screen_confidence: float = 0.0
    bootstrap_ready: bool = False
    run_started: bool = False
    run_ended: bool = False
    skip_ally: bool = False
    """Semantic diff guard: when True, the main loop should bypass the
    Scribe/Ally LLM calls this turn because the confirmed facts are
    identical to last turn's (pixel-level motion detected, but no
    semantic change). State updates still happen so the sandbox stays
    consistent."""


class Collector(Protocol):
    def capture(self) -> RawObservation: ...
