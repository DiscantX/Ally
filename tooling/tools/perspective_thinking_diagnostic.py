"""Standalone diagnostic CLI script for streaming Gemini's thinking trace
and final structured AllyOutput for a single screenshot image.
Never touches real production state/DB (uses in-memory MemoryDB).
"""

import os
import sys
from PIL import Image
from dotenv import load_dotenv

from infrastructure.llm.gemini_provider import GeminiProvider
from brain.perception.scribe import Scribe
from brain.state.sandbox import StateSandbox
from brain.state.entity_registry import EntityRegistry
from brain.reasoning.perspective_engine import PerspectiveEngine
from brain.reasoning.ally_agent import Ally
from brain.knowledge.prompts.ally import ALLY_PROMPT_TEMPLATE
from brain.knowledge.schema.schema import AllyOutput
from brain.memory.db import MemoryDB
from infrastructure.logger import log

load_dotenv(override=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: python tooling/tools/perspective_thinking_diagnostic.py <path/to/image.png>")
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.exists(image_path):
        print(f"Error: Image path '{image_path}' does not exist.")
        sys.exit(1)

    print(f"Loading image from {image_path}...")
    image = Image.open(image_path).convert("RGB")

    provider = GeminiProvider()
    scribe = Scribe(provider)
    sandbox = StateSandbox()
    
    # Use in-memory DB so we never touch real player persisted storage
    db = MemoryDB(db_path=":memory:", player_id="diagnostic_player")
    registry = EntityRegistry(player_id="diagnostic_player", game_id="diagnostic_game", save_id="diag_save", db=db)
    perspective_engine = PerspectiveEngine()
    ally = Ally(provider)

    print("Running Scribe extraction...")
    scribe_output = scribe.extract(image, include_ui=True)

    sandbox.update(scribe_output.screen_elements, [])
    touched_entities = registry.resolve_or_create(scribe_output.screen_elements, sandbox.turn)
    entities_context = registry.as_context(touched_entities, max_entities=20)
    elements_context = sandbox.as_context()
    genre_context = "unknown (not yet determined)"
    memory_context = "(no memory yet -- this is the first turn)"

    recent_turns = []
    entity_facts = [fact for ent in touched_entities for fact in ent.facts[-3:]]
    perspective_score = perspective_engine.score(recent_turns, entity_facts)
    perspective_context = perspective_engine.as_context(perspective_score)

    prompt = ALLY_PROMPT_TEMPLATE.format(
        personality=ally.base_personality,
        genre=genre_context,
        memory=memory_context,
        elements=elements_context,
        entities=entities_context,
        perspectives=perspective_context,
    )

    print("\n--- STREAMING THINKING TRACE ---")
    def on_thought(chunk: str):
        print(chunk, end="", flush=True)

    try:
        final_output = provider.generate_structured_stream(
            model=ally.model,
            contents=[prompt],
            schema=AllyOutput,
            thinking_level=ally.thinking_level,
            on_thought_chunk=on_thought,
        )
    except Exception as e:
        print(f"\nError during streaming generation: {e}")
        sys.exit(1)

    print("\n\n--- FINAL OUTPUT ---")
    print(final_output.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
