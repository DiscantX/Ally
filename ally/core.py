"""AllyCore: GUI-agnostic central manager for application orchestration, state, and event hooks.
"""

import threading
import time
from typing import Any, Optional, Callable, cast
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
from schema.schema import AllyOutput
from state.entity_registry import EntityRegistry
from state.genre_tracker import GenreTracker
from state.sandbox import StateSandbox
from configs.config_manager import load_user_config
from tools.init_config import init_config
from vision.debug_overlay import draw_layout_overlay
from vision.clip_classifier import ClipClassifier
from vision.screen_category_store import ScreenCategoryStore
from logger import log
from tools.display import show_image

TURN_INTERVAL_SECONDS = 0.01


class AllyCore:
    """Central manager handling game capture, Scribe extraction, state sandbox,
    entity registry, genre tracker, memory manager, and Ally agent decision loops,
    with observer hooks for frontends (GUI, CLI, tests).
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        game_id: Optional[str] = None,
        image_path: Optional[str] = None,
        personality_name: Optional[str] = None,
        player_id: str = "default_player",
    ):
        self.player_id = player_id
        config = load_user_config(player_id=player_id)
        self.config_path = config_path
        self.game_id = game_id
        self.image_path = image_path
        self.personality_name = personality_name or config.get("default_personality", "Scout")

        self.provider = GeminiProvider()
        self.scribe = Scribe(self.provider)
        self.ally = Ally(self.provider, base_personality=self.personality_name)
        self.sandbox = StateSandbox()
        self.genre_tracker = GenreTracker()

        self.db = MemoryDB(player_id=player_id)
        self.save_tracker = SaveTracker(self.db)
        self.clip_classifier = ClipClassifier()
        self.category_store = ScreenCategoryStore(db=self.db, clip=self.clip_classifier)
        self.memory_manager: Optional[MemoryManager] = None
        self.registry: Optional[EntityRegistry] = None
        self.collector: Optional[GenericHudCollector] = None
        self.gui_app: Optional[Any] = None

        self.state_lock = threading.Lock()
        self.running = False
        self._loop_thread: Optional[threading.Thread] = None

        # Observer / Event callbacks
        self.on_pipeline_image: Optional[Callable[[str, Image.Image, str], None]] = None
        self.on_debug_overlay: Optional[Callable[[np.ndarray], None]] = None
        self.on_status_update: Optional[Callable[[str, str], None]] = None
        self.on_state_summary: Optional[Callable[[str], None]] = None
        self.on_prompt_update: Optional[Callable[[str], None]] = None
        self.on_feedback: Optional[Callable[[str], None]] = None
        self.on_chat_message: Optional[Callable[[str, str], None]] = None
        self.on_eta_ready: Optional[Callable[[], None]] = None
        self.on_connection_status: Optional[Callable[[bool], None]] = None

    def update_pipeline_image(self, key: str, image, title: Optional[str] = None):
        if self.gui_app is not None and hasattr(self.gui_app, "update_pipeline_image"):
            self.gui_app.update_pipeline_image(key, image, title)
        elif self.on_pipeline_image is not None:
            self.on_pipeline_image(key, image, title)

    def _debug_frame(self, observation: RawObservation) -> np.ndarray:
        if observation.image is None:
            return np.zeros((100, 100, 3), dtype=np.uint8)
        img = observation.image
        frame_bgr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        if self.collector is None:
            return frame_bgr
        reader = self.collector.readers.get(observation.screen_name)
        layout = reader.layout if reader else None
        return draw_layout_overlay(frame_bgr, layout, observation.confirmed_facts)

    def run_turn(self, observation: RawObservation, include_ui: bool = True) -> bool:
        if observation.image is None:
            # log("No image captured -- is the game window open?")
            return False

        if self.on_pipeline_image is not None:
            self.on_pipeline_image("observation", observation.image, "RGB PIL Image Observation")
            if self.collector is not None:
                c_any = cast(Any, self.collector)
                target_gui = self.gui_app or self
                if hasattr(c_any, "change_detector") and c_any.change_detector:
                    c_any.change_detector.gui_app = target_gui
                if hasattr(c_any, "screen") and c_any.screen and hasattr(c_any.screen, "change_detector"):
                    c_any.screen.change_detector.gui_app = target_gui
                if hasattr(c_any, "classifier") and c_any.classifier:
                    c_any.classifier.gui_app = target_gui

        debug_frame = self._debug_frame(observation)
        if self.on_debug_overlay is not None:
            self.on_debug_overlay(debug_frame)
        else:
            show_image(debug_frame)

        log(
            "\n--- Screen: {screen_name} (confidence={confidence:.2f}) ---",
            screen_name=observation.screen_name, confidence=observation.screen_confidence,
        )

        log("--- Scribe extracting ({mode}) ---", mode="NO_UI" if not include_ui else "UI")
        skip_scribe_reason = getattr(observation, 'skip_scribe_reason', 'none')
        skip_ally = getattr(observation, 'skip_ally', False) or skip_scribe_reason != 'none'

        if not skip_ally:
            scribe_output = self.scribe.extract(observation.image, include_ui=include_ui)

            if self.category_store is not None and self.collector is not None:
                self.category_store.maybe_learn(scribe_output.screen_name_guess, self.collector.config.game_id)

            if self.collector is not None and observation.bootstrap_ready:
                self.collector.bootstrap_screen(scribe_output.screen_elements, scribe_output.screen_name_guess)

            with self.state_lock:
                self.sandbox.update(scribe_output.screen_elements, observation.confirmed_facts)
                genre_estimate = self.genre_tracker.update(
                    scribe_output.genre_guess, scribe_output.genre_confidence
                )

                log("\n--- Confirmed facts (OCR, bypassed the Scribe) ---")
                for fact in self.sandbox.confirmed_facts:
                    log("{key}: {value}  (source={source})", key=fact.key, value=fact.value, source=fact.source)

                log("\n--- Screen elements ---")
                for el in self.sandbox.current_elements:
                    log("[{id}] {label}: {description}  box={box}", id=el.id, label=el.label, description=el.description, box=el.box_2d)

                if self.registry is not None:
                    touched_entities = self.registry.resolve_or_create(cast(Any, scribe_output.screen_elements), self.sandbox.turn)
                    entities_context = self.registry.as_context(touched_entities, max_entities=20)
                else:
                    entities_context = "(no registry)"

                elements_context = self.sandbox.as_context()
                genre_context = self.genre_tracker.as_context()
                memory_context = self.memory_manager.build_context() if self.memory_manager else "(no memory)"
                personality_context = self.memory_manager.get_personality_context() if self.memory_manager else self.ally.base_personality

            log("\n--- Entity registry (accumulated across the run) ---")
            log("{}", entities_context)

            log(
                "\n--- Genre: {guess} (confidence={confidence:.2f}, locked={locked}) ---",
                guess=genre_estimate.guess,
                confidence=genre_estimate.confidence,
                locked=genre_estimate.locked
            )

            log("\n--- Ally (blind to the image) ---")
            ally_output = self.ally.decide(
                elements_context=elements_context,
                entities_context=entities_context,
                genre_context=genre_context,
                memory_context=memory_context,
                personality=personality_context,
            )
            log("\nAnalysis:\n{analysis}", analysis=ally_output.analysis)
            log("\nActions:")
            for action in ally_output.actions:
                log("  - {text}", text=action.text)
        else:
            with self.state_lock:
                self.sandbox.update([], observation.confirmed_facts)
                genre_estimate = self.genre_tracker.update("unknown", 0.0)
                if self.registry is not None:
                    touched_entities = self.registry.resolve_or_create([], self.sandbox.turn)
                    entities_context = self.registry.as_context(touched_entities, max_entities=20)
                else:
                    entities_context = "(no registry)"
            log("\n--- Entity registry (accumulated across the run) ---")
            log("{}", entities_context)
            skip_messages = {
                "off_game": f"(CLIP recognized this as off-game content: '{observation.screen_category}' -- pausing commentary)",
                "low_value": f"(CLIP recognized this as a low-value screen: '{observation.screen_category}' -- skipping commentary)",
                "none": "(confirmed facts unchanged this turn -- no new commentary)",
            }
            reason_label = skip_scribe_reason if skip_scribe_reason != "none" else "facts_unchanged"
            log("--- Skipping Scribe/Ally (reason={reason}) ---", reason=reason_label)
            ally_output = AllyOutput(
                analysis=skip_messages.get(skip_scribe_reason, skip_messages["none"]),
                actions=[],
                run_boundary="none",
            )

        with self.state_lock:
            if self.memory_manager is not None and skip_scribe_reason != "off_game":
                self.memory_manager.record_turn(
                    self.sandbox.turn,
                    ally_output.analysis if not skip_ally else f"skip_ally: {reason_label}"
                )

            run_ended = resolve_run_ended(observation, ally_output)
            if run_ended:
                log("\n--- Run ended (boundary resolved) ---")
                if self.memory_manager is not None:
                    self.memory_manager.close_run()
                if self.on_chat_message is not None:
                    self.on_chat_message("coach", "Run ended! Closing session and saving cross-session memories.")

        if self.on_status_update is not None:
            self.on_status_update(observation.screen_name, "turn")
        if self.on_state_summary is not None:
            self.on_state_summary(self.sandbox.as_context())
        if self.on_prompt_update is not None:
            self.on_prompt_update(self.sandbox.as_context()[:300])
        if self.on_feedback is not None:
            self.on_feedback(ally_output.analysis)
        if self.on_eta_ready is not None:
            self.on_eta_ready()

        return run_ended

    def run_loop(self, interval_seconds: float = TURN_INTERVAL_SECONDS) -> None:
        if self.collector is None:
            log("No collector configured for run_loop.")
            return

        log("Starting turn loop (every {interval_seconds}s). Ctrl+C to stop.", interval_seconds=interval_seconds)
        self.running = True
        try:
            while self.running:
                observation = self.collector.capture()
                if observation.image is not None and not observation.changed:
                    pass
                else:
                    reader = self.collector.readers.get(observation.screen_name)
                    include_ui = reader is None or not reader.has_calibrated_fields
                    ended = self.run_turn(observation, include_ui=include_ui)
                    if ended and self.memory_manager is not None and self.registry is not None:
                        log("Run concluded. Starting new run session...")
                        player_id = self.memory_manager.player_id
                        game_id = self.memory_manager.game_id
                        new_save_id, _ = self.save_tracker.resolve_save_id(player_id=player_id, game_id=game_id)
                        self.memory_manager.narrative = NarrativeMemoryManager(
                            player_id=player_id,
                            game_id=game_id,
                            save_id=new_save_id,
                            provider=self.memory_manager.narrative.provider,
                            db=self.memory_manager.db,
                            short_term_capacity=self.memory_manager.narrative.short_term_capacity,
                            flush_trigger=self.memory_manager.narrative.flush_trigger,
                            save_tracker=self.save_tracker,
                        )
                        self.registry.__init__(
                            player_id=player_id,
                            game_id=game_id,
                            save_id=new_save_id,
                            db=self.db,
                        )
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            log("\nStopping loop.")
        finally:
            self.stop()

    def stop(self) -> None:
        self.running = False
        try:
            if self.memory_manager is not None:
                self.memory_manager.close_run()
        except Exception:
            pass

    def send_message(self, text: str, message_type: str = "chat") -> None:
        """Asynchronously handles chat messages and feedback submissions from the frontend."""
        def _handle():
            memory_context = ""
            personality_context = ""
            entities_context = "(no known entities yet)"
            elements_context = ""
            genre_context = ""
            not_started = False

            with self.state_lock:
                if self.memory_manager is None:
                    not_started = True
                else:
                    if message_type != "feedback":
                        entities_context = self.registry.as_context(list(self.registry._entities.values())) if self.registry else "(no known entities yet)"
                        elements_context = self.sandbox.as_context()
                        genre_context = self.genre_tracker.as_context()
                        memory_context = self.memory_manager.build_context()
                        personality_context = self.memory_manager.get_personality_context()
                    else:
                        self.memory_manager.personality.record_reflection(f"Player feedback: {text}")

            if not_started:
                if self.on_chat_message is not None:
                    self.on_chat_message("coach", "Game loop hasn't started yet. Hang tight!")
                return

            if message_type == "feedback":
                if self.on_chat_message is not None:
                    self.on_chat_message("coach", "Got it! I've noted that feedback and adjusted my approach.")
                return

            try:
                res = self.ally.chat(
                    elements_context=elements_context,
                    entities_context=entities_context,
                    genre_context=genre_context,
                    memory_context=memory_context,
                    personality=personality_context,
                    question=text,
                )
                with self.state_lock:
                    if self.memory_manager is not None:
                        self.memory_manager.record_turn(
                            self.sandbox.turn,
                            f"Player asked: '{text}' -> Ally answered: '{res.response}'",
                            importance=5
                        )
                if self.on_chat_message is not None:
                    self.on_chat_message("coach", res.response)
            except Exception as e:
                if self.on_chat_message is not None:
                    self.on_chat_message("coach", f"(Error: {e})")

        threading.Thread(target=_handle, daemon=True).start()

    def initialize_run(self) -> None:
        """Initializes memory manager, registry, and collector based on provided args/config."""
        player_id = "default_player"
        if self.image_path:
            save_id, _ = self.save_tracker.resolve_save_id(player_id=player_id, game_id="adhoc_image")
            self.memory_manager = MemoryManager(
                player_id=player_id,
                game_id="adhoc_image",
                save_id=save_id,
                provider=self.provider,
                base_personality=self.ally.base_personality,
                save_tracker=self.save_tracker,
            )
            self.registry = EntityRegistry(
                player_id=player_id,
                game_id="adhoc_image",
                save_id=save_id,
                db=self.db,
            )
        else:
            if not self.config_path:
                self.config_path = init_config(game_id=self.game_id)
            self.collector = build_collector(
                self.config_path,
                clip_classifier=self.clip_classifier,
                category_store=self.category_store,
            )
            game_id = self.collector.config.game_id
            save_id, _ = self.save_tracker.resolve_save_id(player_id=player_id, game_id=game_id)
            self.memory_manager = MemoryManager(
                player_id=player_id,
                game_id=game_id,
                save_id=save_id,
                provider=self.provider,
                base_personality=self.ally.base_personality,
                save_tracker=self.save_tracker,
            )
            self.registry = EntityRegistry(
                player_id=player_id,
                game_id=game_id,
                save_id=save_id,
                db=self.db,
            )



