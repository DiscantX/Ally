"""The State Sandbox: a plain Python record of the current screen.

Deliberately dumb. It doesn't call any model, doesn't decide anything --
it just holds what the Scribe most recently reported, plus any
ConfirmedFacts a Collector supplied directly (e.g. calibrated OCR), plus
(new in this pass) an optional structured_state payload for Collectors
whose data isn't a flat per-turn overwrite at all, so Ally has something
stable to read from.

Three kinds of data, three different trust/lifecycle framings:

- `current_elements` (Scribe's screen_elements): an LLM's interpretation
  of an image. Fully overwritten every turn -- last turn's elements
  don't describe this turn's screen.
- `confirmed_facts` (calibrated OCR, or any Collector-supplied exact
  reading): read with certainty, presented to Ally as such. Also fully
  overwritten every turn -- it's this turn's readings, not a running
  total.
- `structured_state` (e.g. MTGA's parsed Full+Diff game_state): data
  read directly from a game's own protocol/API rather than interpreted
  or OCR'd -- per ally_decision_log.md and mtga_integration_notes.md
  §5.4, this is at least as trustworthy as calibrated OCR, arguably more
  so (it's not a crop-and-recognize step over pixels at all). Unlike the
  two lists above, it is NOT reset when a turn's update() call omits it
  -- the owning Collector (e.g. MTGALogParser) maintains it as a running
  accumulation across the whole run and hands StateSandbox a reference
  to its current state each time something changed, not a full replay
  every turn. StateSandbox doesn't know or care what's inside it beyond
  that it's a dict; rendering in as_context() is deliberately generic
  (key + a count/type summary per top-level entry) rather than assuming
  any particular game's shape.
"""

import threading
from typing import Any

from ingestion.collectors.base import ConfirmedFact
from brain.knowledge.schema.schema import ScreenElement


def _summarize_structured_value(value: Any) -> str:
    """Compact one-line summary for a top-level structured_state entry.
    Deliberately generic (count/type based, not field-aware) -- Sandbox
    doesn't know the shape of any particular Collector's payload, and
    shouldn't have to in order to render *something* useful."""
    if isinstance(value, dict):
        return f"{{...}} ({len(value)} entries)"
    if isinstance(value, list):
        return f"[...] ({len(value)} items)"
    return str(value)


class StateSandbox:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.turn: int = 0
        self.current_elements: list[ScreenElement] = []
        self.confirmed_facts: list[ConfirmedFact] = []
        self.structured_state: dict[str, Any] | None = None
        self.structured_state_source: str | None = None

    def update(
        self,
        elements: list[ScreenElement],
        confirmed_facts: list[ConfirmedFact] | None = None,
        structured_state: dict[str, Any] | None = None,
        structured_state_source: str | None = None,
    ) -> None:
        with self._lock:
            self.turn += 1
            self.current_elements = elements
            self.confirmed_facts = confirmed_facts or []

            # structured_state is deliberately NOT reset to None here when
            # omitted -- see module docstring. A turn where the Collector
            # doesn't pass one (or isn't a structured-state Collector at all,
            # e.g. the existing screen-capture path) shouldn't wipe out what
            # a structured Collector already accumulated.
            if structured_state is not None:
                self.structured_state = structured_state
                self.structured_state_source = structured_state_source

    def as_context(self) -> str:
        """Compact text form for injecting into Ally's prompt.
        
        Thread-safe: holds read lock while building context string.
        """
        with self._lock:
            parts = []

            if self.confirmed_facts:
                parts.append("Confirmed exact readings (not an interpretation, trust these):")
                parts.extend(f"- {fact.key}: {fact.value}" for fact in self.confirmed_facts)

            if self.structured_state:
                if parts:
                    parts.append("")
                source_note = f" (source: {self.structured_state_source})" if self.structured_state_source else ""
                parts.append(
                    f"Structured game state{source_note} -- read directly from the "
                    "game's own protocol/data, not an interpretation. Trust this at "
                    "least as much as the confirmed readings above:"
                )
                parts.extend(
                    f"- {key}: {_summarize_structured_value(value)}"
                    for key, value in self.structured_state.items()
                )

            if self.current_elements:
                if parts:
                    parts.append("")
                parts.append("Scene elements (Scribe's interpretation):")
                # Filter out decorative elements, but preserve anything referenced by target_entity_ids
                # Note: We don't have access to previous turn's AllyOutput here, so we filter based on is_decorative flag
                # The safety check for target_entity_ids must be done elsewhere (e.g., in main.py or Scribe)
                filtered_elements = []
                for el in self.current_elements:
                    if hasattr(el, 'is_decorative') and el.is_decorative:
                        continue
                    filtered_elements.append(el)
                parts.extend(
                    f"- [{el.id}] {el.label}: {el.description}" for el in filtered_elements
                )

            return "\n".join(parts) if parts else "(no elements on screen)"