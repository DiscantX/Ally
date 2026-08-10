"""Vertical slice: one full turn through the pipeline, now via a real
Collector instead of opening an image file directly.

    Collector (screen capture + calibrated OCR)
        -> Scribe (sees image, extracts scene elements)
        -> State Sandbox (holds this turn's facts + OCR ConfirmedFacts)
        -> Entity Registry (resolves facts against everything seen so far)
        -> Ally (blind to the image, reasons from facts + entities only)

Usage:
    python main.py                 # live capture via SlayTheSpireCollector
    python main.py images/monkey.png   # still supported: file-backed run
"""

import sys

from PIL import Image

from ally.ally_agent import Ally
from ally.personalities import PERSONALITIES
from collectors.base import RawObservation
from interpretation.scribe import Scribe
from llm.gemini_provider import GeminiProvider
from plugins.slay_the_spire.collector import SlayTheSpireCollector
from state.entity_registry import EntityRegistry
from state.sandbox import StateSandbox
from state.genre_tracker import GenreTracker


def run_turn(observation: RawObservation, genre_tracker: GenreTracker) -> None:
    if observation.image is None:
        print("No image captured -- is the game window open?")
        return

    provider = GeminiProvider()
    scribe = Scribe(provider)
    ally = Ally(provider, PERSONALITIES["Scout"])
    sandbox = StateSandbox()
    registry = EntityRegistry()

    print("--- Scribe extracting ---")
    scribe_output = scribe.extract(observation.image)
    sandbox.update(scribe_output.screen_elements, observation.confirmed_facts)
    genre_tracker.update(scribe_output.genre_guess, scribe_output.genre_confidence)

    print("\n--- Confirmed facts (OCR, bypassed the Scribe) ---")
    for fact in sandbox.confirmed_facts:
        print(f"{fact.key}: {fact.value}  (source={fact.source})")

    print("\n--- Screen elements ---")
    for el in sandbox.current_elements:
        print(f"[{el.id}] {el.label}: {el.description}  box={el.box_2d}")

    touched_entities = registry.resolve_or_create(scribe_output.screen_elements, sandbox.turn)
    entities_context = registry.as_context(touched_entities)

    print("\n--- Entity registry (this turn) ---")
    print(entities_context)

    print("\n--- Ally (blind to the image) ---")
    ally_output = ally.decide(
        elements_context=sandbox.as_context(),
        entities_context=entities_context,
        genre_context=genre_tracker.as_context(),
    )
    print("\nAnalysis:")
    print(ally_output.analysis)
    print("\nActions:")
    for action in ally_output.actions:
        print(f"  - {action.text}")


if __name__ == "__main__":
    genre_tracker = GenreTracker()  # lives here, not inside run_turn, so a
                                     # future loop can pass the same one in
                                     # on every iteration
    if len(sys.argv) > 1:
        run_turn(RawObservation(image=Image.open(sys.argv[1])), genre_tracker)
    else:
        collector = SlayTheSpireCollector()
        run_turn(collector.capture(), genre_tracker)
