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

Game selection (new in this pass): main.py no longer hardcodes a single
game's config path. --game <game_id> looks up configs/<game_id>/config.json
and, if it doesn't exist yet, auto-creates it from the currently focused
window via tools/init_config.py -- so onboarding a brand-new screen-capture
game requires zero hand-written JSON, only having that game's window
focused the first time you run it. This is the "just play FTL" path: no
plugin, no layout calibration required to start (an uncalibrated layout
just means Scribe runs in full-UI mode until ScreenBootstrapper drafts one
on its own).

Usage:
    python main.py --game ftl            # auto-creates configs/ftl/config.json
                                          # from the focused window if missing,
                                          # then runs the live loop
    python main.py                       # same, but derives game_id from
                                          # whatever window is focused right now
    python main.py --config path/to.json # explicit config path, skips --game
                                          # lookup/auto-create entirely
    python main.py images/monkey.png     # still supported: single file-backed
                                          # run, no loop
"""

from typing import Any, cast
import argparse
import sys
import time
import uuid

import cv2
import numpy as np
from PIL import Image

from ally.ally_agent import Ally
from ally.personalities import PERSONALITIES
from collectors.base import RawObservation
from collectors.configured_collector import build_collector, GenericHudCollector
from interpretation.scribe import Scribe
from llm.gemini_provider import GeminiProvider
from memory.manager import MemoryManager
from memory.db import MemoryDB
from memory.save_tracker import SaveTracker
from memory.triggers import resolve_run_ended
from memory.narrative import NarrativeMemoryManager
from state.entity_registry import EntityRegistry
from state.genre_tracker import GenreTracker
from state.sandbox import StateSandbox
from tools.init_config import init_config
from vision.debug_overlay import draw_layout_overlay
from logger import log
from tools.display import show_image

# How often to capture + process a turn during the live loop. Tune this
# against two competing costs: snappier feel (lower) vs. Gemini RPD/RPM
# budget and per-call latency, especially once thinking mode is enabled
# on the Scribe for dense scenes (see ally_decision_log.md).
TURN_INTERVAL_SECONDS = 0.01


def _debug_frame(observation: RawObservation, collector: GenericHudCollector | None) -> np.ndarray:
    """Builds the frame shown in the debug window: the raw capture with
    the current screen's calibrated OCR boxes -- and this turn's
    extracted values -- drawn on top, when a collector/reader is
    available. Lets misaligned or misread boxes be diagnosed by eye
    during actual play, without a separate run of tools/inspect_coords.py.
    Falls back to the plain frame when there's no collector (single-image
    mode) or no reader for this screen yet (unrecognized/uncalibrated)."""
    if observation.image is None:
        return np.zeros((100, 100, 3), dtype=np.uint8)
    img = observation.image
    frame_bgr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    if collector is None:
        return frame_bgr
    reader = collector.readers.get(observation.screen_name)
    layout = reader.layout if reader else None
    return draw_layout_overlay(frame_bgr, layout, observation.confirmed_facts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ally vertical slice runner.")
    parser.add_argument(
        "image", nargs="?",
        help="Path to a single image file -- back-compat single-shot mode, no loop.",
    )
    parser.add_argument(
        "--game",
        help="game_id to run (e.g. 'ftl'). Looks up configs/<game_id>/config.json, "
             "auto-creating it from the currently focused window if it doesn't exist yet. "
             "Omit entirely to derive game_id from whatever window is focused right now.",
    )
    parser.add_argument(
        "--config",
        help="Explicit path to a config.json. Overrides --game entirely -- no "
             "auto-create, the file must already exist.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the standalone Ally GUI overlay.",
    )
    return parser.parse_args()


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
    gui_app = None,
) -> bool:
    if observation.image is None:
        log("No image captured -- is the game window open?")
        return False

    if gui_app is not None:
        gui_app.update_pipeline_image("observation", observation.image, "RGB PIL Image Observation")
        if collector is not None:
            c_any = cast(Any, collector)
            if hasattr(c_any, "change_detector") and c_any.change_detector:
                c_any.change_detector.gui_app = gui_app
            if hasattr(c_any, "screen") and c_any.screen and hasattr(c_any.screen, "change_detector"):
                c_any.screen.change_detector.gui_app = gui_app
            if hasattr(c_any, "classifier") and c_any.classifier:
                c_any.classifier.gui_app = gui_app

    debug_frame = _debug_frame(observation, collector)
    if gui_app is not None:
        gui_app.update_pipeline_image("debug_overlay", debug_frame, "Annotated Debug Overlay Frame")
    else:
        show_image(debug_frame)

    log(
        "\n--- Screen: {screen_name} (confidence={confidence:.2f}) ---",
        screen_name=observation.screen_name, confidence=observation.screen_confidence,
    )

    log("--- Scribe extracting ({mode}) ---", mode="NO_UI" if not include_ui else "UI")
    # Semantic diff guard: if confirmed facts haven't changed, skip Scribe/Ally
    skip_ally = getattr(observation, 'skip_ally', False)

    if not skip_ally:
        # Move Scribe/Ally calls to a separate thread
        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=1)

        def _inference_task():
            return scribe.extract(observation.image, include_ui=include_ui)

        future = executor.submit(_inference_task)
        scribe_output = future.result()

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

        touched_entities = registry.resolve_or_create(cast(Any, scribe_output.screen_elements), sandbox.turn)
        entities_context = registry.as_context(touched_entities, max_entities=20)

        log("\n--- Entity registry (accumulated across the run) ---")
        log("{}", entities_context)

        log(
            "\n--- Genre: {guess} (confidence={confidence:.2f}, locked={locked}) ---",
            guess=genre_estimate.guess,
            confidence=genre_estimate.confidence,
            locked=genre_estimate.locked
        )

        log("\n--- Ally (blind to the image) ---")
        def _ally_task():
            return ally.decide(
                elements_context=sandbox.as_context(),
                entities_context=entities_context,
                genre_context=genre_tracker.as_context(),
                memory_context=memory_manager.build_context(),
                personality=memory_manager.get_personality_context(),
            )
        
        ally_future = executor.submit(_ally_task)
        ally_output = ally_future.result()
        executor.shutdown()
        log("\nAnalysis:\n{analysis}", analysis=ally_output.analysis)
        log("\nActions:")
        for action in ally_output.actions:
            log("  - {text}", text=action.text)
    else:
        # Skip Scribe/Ally invocation but maintain state consistency
        sandbox.update([], observation.confirmed_facts)
        genre_estimate = genre_tracker.update("unknown", 0.0)
        touched_entities = registry.resolve_or_create([], sandbox.turn)
        entities_context = registry.as_context(touched_entities, max_entities=20)
        log("\n--- Entity registry (accumulated across the run) ---")
        log("{}", entities_context)
        log("--- Skipping Scribe/Ally (confirmed facts unchanged) ---")

    memory_manager.record_turn(sandbox.turn, ally_output.analysis if not skip_ally else "skip_ally: confirmed facts unchanged")

    run_ended = resolve_run_ended(observation, ally_output)
    if run_ended:
        log("\n--- Run ended (boundary resolved) ---")
        memory_manager.close_run()
        if gui_app is not None:
            gui_app.append_chat_message("coach", "Run ended! Closing session and saving cross-session memories.")

    if gui_app is not None:
        gui_app.update_debug_info(observation.screen_name, "turn")
        gui_app.update_state_summary(sandbox.as_context())
        gui_app.update_prompt(sandbox.as_context()[:300])
        gui_app.update_feedback(ally_output.analysis)
        gui_app.set_eta_ready()

    return run_ended


def run_loop(
    collector: GenericHudCollector,
    scribe: Scribe,
    ally: Ally,
    sandbox: StateSandbox,
    registry: EntityRegistry,
    genre_tracker: GenreTracker,
    memory_manager: MemoryManager,
    save_tracker: SaveTracker,
    db: MemoryDB,
    player_id: str,
    game_id: str,
    interval_seconds: float = TURN_INTERVAL_SECONDS,
    gui_app = None,
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
                ended = run_turn(
                    observation, scribe, ally, sandbox, registry, genre_tracker, memory_manager,
                    collector=collector, include_ui=include_ui, gui_app=gui_app,
                )
                if ended:
                    log("Run concluded. Starting new run session...")
                    new_save_id, _ = save_tracker.resolve_save_id(player_id=player_id, game_id=game_id)
                    memory_manager.narrative = NarrativeMemoryManager(
                        player_id=player_id,
                        game_id=game_id,
                        save_id=new_save_id,
                        provider=memory_manager.narrative.provider,
                        db=memory_manager.db,
                        short_term_capacity=memory_manager.narrative.short_term_capacity,
                        flush_trigger=memory_manager.narrative.flush_trigger,
                        save_tracker=save_tracker,
                    )
                    registry.__init__(
                        player_id=player_id,
                        game_id=game_id,
                        save_id=new_save_id,
                        db=db,
                    )
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        log("\nStopping loop.")
    finally:
        try:
            memory_manager.close_run()
        except Exception:
            pass


if __name__ == "__main__":
    args = parse_args()

    provider = GeminiProvider()
    scribe = Scribe(provider)
    ally = Ally(provider, PERSONALITIES["Scout"])
    sandbox = StateSandbox()
    genre_tracker = GenreTracker()

    gui_app = None
    state = {"memory_manager": None, "registry": None}

    def on_send_message(text: str, message_type: str):
        def _handle():
            mm = state["memory_manager"]
            reg = state["registry"]
            if not mm:
                if gui_app:
                    gui_app.append_chat_message("coach", "Game loop hasn't started yet. Hang tight!")
                return

            if message_type == "feedback":
                mm.personality.record_reflection(f"Player feedback: {text}")
                if gui_app:
                    gui_app.append_chat_message("coach", "Got it! I've noted that feedback and adjusted my approach.")
            else:
                try:
                    entities_context = reg.as_context(list(reg._entities.values())) if reg else "(no known entities yet)"
                    res = ally.chat(
                        elements_context=sandbox.as_context(),
                        entities_context=entities_context,
                        genre_context=genre_tracker.as_context(),
                        memory_context=mm.build_context(),
                        personality=mm.get_personality_context(),
                        question=text,
                    )
                    mm.record_turn(sandbox.turn, f"Player asked: '{text}' -> Ally answered: '{res.response}'", importance=5)
                    if gui_app:
                        gui_app.append_chat_message("coach", res.response)
                except Exception as e:
                    if gui_app:
                        gui_app.append_chat_message("coach", f"(Error: {e})")

        import threading
        threading.Thread(target=_handle, daemon=True).start()

    if args.gui:
        from gui.tkinter_app import AllyOverlay
        gui_app = AllyOverlay(on_send_message=on_send_message)
        gui_app.set_connection_status(True)

    def execute_run():
        db = MemoryDB()
        save_tracker = SaveTracker(db)
        if args.image:
            # Back-compat: single file-backed run, no loop -- looping on a
            # static image file doesn't mean anything.
            save_id, _ = save_tracker.resolve_save_id(player_id="default_player", game_id="adhoc_image")
            memory_manager = MemoryManager(
                player_id="default_player",
                game_id="adhoc_image",
                save_id=save_id,
                provider=provider,
                base_personality=ally.base_personality,
                save_tracker=save_tracker,
            )
            state["memory_manager"] = memory_manager
            registry = EntityRegistry(
                player_id="default_player",
                game_id="adhoc_image",
                save_id=save_id,
                db=db,
            )
            state["registry"] = registry
            observation = RawObservation(image=Image.open(args.image))
            ended = run_turn(observation, scribe, ally, sandbox, registry, genre_tracker, memory_manager, gui_app=gui_app)
            if not ended:
                try:
                    memory_manager.close_run()
                except Exception:
                    pass
        else:
            if args.config:
                config_path = args.config
            else:
                # Auto-creates configs/<game_id>/config.json from the focused
                # window if it doesn't exist yet; no-ops (just returns the
                # path) if it's already there. See tools/init_config.py.
                config_path = init_config(game_id=args.game)

            collector = build_collector(config_path)
            player_id = "default_player"
            game_id = collector.config.game_id
            save_id, _ = save_tracker.resolve_save_id(player_id=player_id, game_id=game_id)
            memory_manager = MemoryManager(
                player_id=player_id,
                game_id=game_id,
                save_id=save_id,
                provider=provider,
                base_personality=ally.base_personality,
                save_tracker=save_tracker,
            )
            state["memory_manager"] = memory_manager
            registry = EntityRegistry(
                player_id=player_id,
                game_id=game_id,
                save_id=save_id,
                db=db,
            )
            state["registry"] = registry
            run_loop(collector, scribe, ally, sandbox, registry, genre_tracker, memory_manager, save_tracker, db, player_id, game_id, gui_app=gui_app)

    if args.gui:
        import threading
        threading.Thread(target=execute_run, daemon=True).start()
        if gui_app is not None:
            gui_app.mainloop()
    else:
        execute_run()
