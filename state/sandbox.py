"""The State Sandbox: a plain Python record of the current screen.

Deliberately dumb. It doesn't call any model, doesn't decide anything --
it just holds what the Scribe most recently reported, plus any
ConfirmedFacts a Collector supplied directly (e.g. calibrated OCR),
so Ally has something stable to read from.

ConfirmedFacts are kept in their own list, not merged into
current_elements, because they carry a different epistemic status: the
Scribe's elements are an LLM's interpretation of an image, while
ConfirmedFacts are read with certainty and should be presented to Ally
as such.
"""

from collectors.base import ConfirmedFact
from schema.schema import ScreenElement


class StateSandbox:
    def __init__(self):
        self.turn: int = 0
        self.current_elements: list[ScreenElement] = []
        self.confirmed_facts: list[ConfirmedFact] = []

    def update(
        self,
        elements: list[ScreenElement],
        confirmed_facts: list[ConfirmedFact] | None = None,
    ) -> None:
        self.turn += 1
        self.current_elements = elements
        self.confirmed_facts = confirmed_facts or []

    def as_context(self) -> str:
        """Compact text form for injecting into Ally's prompt."""
        parts = []

        if self.confirmed_facts:
            parts.append("Confirmed exact readings (not an interpretation, trust these):")
            parts.extend(f"- {fact.key}: {fact.value}" for fact in self.confirmed_facts)

        if self.current_elements:
            if parts:
                parts.append("")
            parts.append("Scene elements (Scribe's interpretation):")
            parts.extend(
                f"- [{el.id}] {el.label}: {el.description}" for el in self.current_elements
            )

        return "\n".join(parts) if parts else "(no elements on screen)"
