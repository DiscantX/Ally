"""Vertical slice: a continuous turn loop through the pipeline.

    Collector (screen capture + calibrated OCR)
        -> Scribe (sees image, extracts scene elements + genre guess)
        -> State Sandbox (holds this turn's facts + OCR ConfirmedFacts)
        -> Entity Registry (resolves facts against everything seen so far)
        -> Genre Tracker (accumulates confidence across turns)
        -> Memory Manager (short-term rolling buffer of recent turns)
        -> Ally (blind to the image, reasons from facts + entities +
                 genre + memory)

EntityRegistry, GenreTracker, and MemoryManager are constructed once,
outside the loop, and threaded through every call to run_turn(). This is
what makes entity resolution, genre confidence, and memory actually
accumulate across turns instead of silently resetting each time -- the
previous version of this file built a fresh EntityRegistry inside
run_turn() itself, which meant "accumulates across a run" was aspirational
since the function only ever ran once.

Usage:
    python main.py                      # live capture loop via SlayTheSpireCollector
    python main.py images/monkey.png    # still supported: single file-backed run, no loop
"""

import sys
import time
import uuid

from PIL import Image

from ally.ally_agent import Ally
from ally.personalities import PERSONALITIES
from collectors.base import RawObservation
from collectors.configured_collector import build_collector, GenericHudCollector
from interpretation.scribe import Scribe
from llm.gemini_provider import GeminiProvider
from memory.manager import MemoryManager
from state.entity_registry import EntityRegistry
from state.genre_tracker import GenreTracker
from state.sandbox import StateSandbox
from logger import log
from tools.display import show_image

# How often to capture + process a turn during the live loop. Tune this
# against two competing costs: snappier feel (lower) vs. Gemini RPD/RPM
# budget and per-call latency, especially once thinking mode is enabled
# on the Scribe for dense scenes (see ally_decision_log.md).
TURN_INTERVAL_SECONDS =0.1


def run_turn(
    observation: RawObservation,
    scribe: Scribe,
    ally: Ally,
    sandbox: StateSandbox,
    registry: EntityRegistry,
    genre_tracker: GenreTracker,
    memory_manager: MemoryManager,
    collector: GenericHudCollector | None = None,
    include_ui: bool = True,
) -> None:
    if observation.image is None:
        log("No image captured -- is the game window open?")
        return

    show_image(observation.image)

    log(
        "\n--- Screen: {screen_name} (confidence={confidence:.2f}) ---",
        screen_name=observation.screen_name, confidence=observation.screen_confidence,
    )

    log("--- Scribe extracting ({mode}) ---", mode="NO_UI" if not include_ui else "UI")
    scribe_output = scribe.extract(observation.image, include_ui=include_ui)

    if collector is not None and observation.bootstrap_ready:
        collector.bootstrap_screen(scribe_output.screen_elements, scribe_output.screen_name_guess)

    sandbox.update(scribe_output.screen_elements, observation.confirmed_facts)
    genre_estimate = genre_tracker.update(
        scribe_output.genre_guess, scribe_output.genre_confidence
    )

    log("\n--- Confirmed facts (OCR, bypassed the Scribe) ---")
    for fact in sandbox.confirmed_facts:
        log("{key}: {value}  (source={source})", key=fact.key, value=fact.value, source=fact.source)

    log("\n--- Screen elements ---")
    for el in sandbox.current_elements:
        log("[{id}] {label}: {description}  box={box}", id=el.id, label=el.label, description=el.description, box=el.box_2d)

    touched_entities = registry.resolve_or_create(scribe_output.screen_elements, sandbox.turn)
    entities_context = registry.as_context(touched_entities)

    log("\n--- Entity registry (accumulated across the run) ---")
    log("{}", entities_context)

    log(
        "\n--- Genre: {guess} (confidence={confidence:.2f}, locked={locked}) ---",
        guess=genre_estimate.guess,
        confidence=genre_estimate.confidence,
        locked=genre_estimate.locked
    )

    log("\n--- Ally (blind to the image) ---")
    ally_output = ally.decide(
        elements_context=sandbox.as_context(),
        entities_context=entities_context,
        genre_context=genre_tracker.as_context(),
        memory_context=memory_manager.build_context(),
    )
    log("\nAnalysis:\n{analysis}", analysis=ally_output.analysis)
    log("\nActions:")
    for action in ally_output.actions:
        log("  - {text}", text=action.text)

    memory_manager.record_turn(sandbox.turn, ally_output.analysis)


def run_loop(
    collector: GenericHudCollector,
    scribe: Scribe,
    ally: Ally,
    sandbox: StateSandbox,
    registry: EntityRegistry,
    genre_tracker: GenreTracker,
    memory_manager: MemoryManager,
    interval_seconds: float = TURN_INTERVAL_SECONDS,
) -> None:
    log("Starting turn loop (every {interval_seconds}s). Ctrl+C to stop.", interval_seconds=interval_seconds)
    try:
        while True:
            observation = collector.capture()
            if observation.image is not None and not observation.changed:
                pass
            else:
                reader = collector.readers.get(observation.screen_name)
                include_ui = reader is None or not reader.has_calibrated_fields
                run_turn(
                    observation, scribe, ally, sandbox, registry, genre_tracker, memory_manager,
                    collector=collector, include_ui=include_ui,
                )
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        log("\nStopping loop.")
    finally:
        memory_manager.flush_to_cross_session()


if __name__ == "__main__":
    provider = GeminiProvider()
    scribe = Scribe(provider)
    ally = Ally(provider, PERSONALITIES["Scout"])
    sandbox = StateSandbox()
    registry = EntityRegistry()
    genre_tracker = GenreTracker()
    memory_manager = MemoryManager(
        player_id="default_player",
        game_id="slay_the_spire",
        save_id=f"session_{uuid.uuid4().hex[:8]}",
    )

    if len(sys.argv) > 1:
        # Back-compat: single file-backed run, no loop -- looping on a
        # static image file doesn't mean anything.
        observation = RawObservation(image=Image.open(sys.argv[1]))
        run_turn(observation, scribe, ally, sandbox, registry, genre_tracker, memory_manager)
    else:
        collector = build_collector("configs/slay_the_spire/config.json")
        run_loop(collector, scribe, ally, sandbox, registry, genre_tracker, memory_manager)