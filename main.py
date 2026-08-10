"""Vertical slice: one full turn through the pipeline.

    Scribe (sees image, extracts facts)
        -> State Sandbox (holds this turn's facts)
        -> Entity Registry (resolves facts against everything seen so far)
        -> Ally (blind to the image, reasons from facts + entities only)

Usage:
    python main.py images/monkey.png
    python main.py images/disco.jpg
"""

import sys

from PIL import Image

from ally.ally_agent import Ally
from interpretation.scribe import Scribe
from llm.gemini_provider import GeminiProvider
from state.entity_registry import EntityRegistry
from state.sandbox import StateSandbox


def run_turn(image_path: str) -> None:
    provider = GeminiProvider()
    scribe = Scribe(provider)
    ally = Ally(provider)
    sandbox = StateSandbox()
    registry = EntityRegistry()

    image = Image.open(image_path)

    print(f"--- Scribe extracting from {image_path} ---")
    scribe_output = scribe.extract(image)
    sandbox.update(scribe_output.screen_elements)

    print("\n--- Screen elements ---")
    for el in sandbox.current_elements:
        print(f"[{el.id}] {el.label}: {el.description}  box={el.box_2d}")

    touched_entities = registry.resolve_or_create(
        scribe_output.screen_elements, sandbox.turn
    )
    entities_context = registry.as_context(touched_entities)

    print("\n--- Entity registry (this turn) ---")
    print(entities_context)

    print("\n--- Ally (blind to the image) ---")
    ally_output = ally.decide(
        elements_context=sandbox.as_context(),
        entities_context=entities_context,
    )
    print("\nAnalysis:")
    print(ally_output.analysis)
    print("\nActions:")
    for action in ally_output.actions:
        print(f"  - {action.text}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "images/monkey.png"
    run_turn(path)
