"""AllyCore: GUI-agnostic central manager for application orchestration, state, and event hooks.
"""

import threading
import time
from collections import deque
from typing import Any, Optional, Callable, cast
import cv2
import numpy as np
from PIL import Image

from brain.constants import ADHOC_IMAGE_GAME_ID, DEFAULT_PLAYER_ID
from utils.event_hook import EventHook
from brain.state.turn_trace import TurnTrace
from brain.reasoning.ally_agent import Ally
from brain.reasoning.personalities import PERSONALITIES
from ingestion.collectors.base import RawObservation
from ingestion.collectors.configured_collector import build_collector, GenericHudCollector
from brain.perception.scribe import Scribe
from infrastructure.llm.providers.gemini_provider import GeminiProvider
from brain.memory.manager import MemoryManager
from brain.memory.db import MemoryDB
from brain.memory.save_tracker import SaveTracker
from brain.memory.triggers import resolve_run_ended, CompositeTrigger, TurnCountTrigger, SalienceEventTrigger, SignificantMomentTrigger, PerspectiveConflictTrigger
from brain.memory.narrative import NarrativeMemoryManager
from brain.knowledge.schema.schema import AllyOutput
from brain.state.entity_registry import EntityRegistry
from brain.state.genre_tracker import GenreTracker
from brain.state.sandbox import StateSandbox
from brain.reasoning.perspective_engine import PerspectiveEngine
from cabinet.configs.config_manager import load_user_config
from cabinet.configs.init_config import init_config
from brain.perception.debug_overlay import draw_layout_overlay
from brain.perception.clip_classifier import ClipClassifier
from brain.perception.screen_category_store import ScreenCategoryStore
from infrastructure.logger import log, timed
from tooling.tools.display import show_image

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
    ) -> None:
        self.player_id = player_id
        config = load_user_config(player_id=player_id)
        self.config_path = config_path
        self.game_id = game_id
        self.image_path = image_path
        self.personality_name = personality_name or config.get("default_personality", "Scout")

        self.provider = GeminiProvider()
        self.scribe = Scribe(self.provider)
        self.ally = Ally(self.provider, base_personality=self.personality_name)
        self.perspective_engine = PerspectiveEngine()
        self.sandbox = StateSandbox()
        self.genre_tracker = GenreTracker()

        self.db = MemoryDB(player_id=player_id)
        self.save_tracker = SaveTracker(self.db)
        self.clip_classifier = ClipClassifier()
        self.category_store = ScreenCategoryStore(db=self.db, clip=self.clip_classifier)
        
        # Validate critical dependencies
        if self.db is None:
            raise RuntimeError("Failed to initialize MemoryDB")
        if self.save_tracker is None:
            raise RuntimeError("Failed to initialize SaveTracker")
        self.memory_manager: Optional[MemoryManager] = None
        self.registry: Optional[EntityRegistry] = None

        self.collector: Optional[GenericHudCollector] = None
        self.gui_app: Optional[Any] = None

        self.state_lock = threading.RLock()
        self._initialization_lock = threading.Lock()
        self._initialized = False
        self.running = False
        self._loop_thread: Optional[threading.Thread] = None

        # Telemetry ring buffer
        self.turn_traces: deque[TurnTrace] = deque(maxlen=20)

        self.personality_flush_trigger = CompositeTrigger([
            TurnCountTrigger(interval=config.get("personality_journal_turn_interval", 20)),
            SalienceEventTrigger(importance_threshold=8),
            SignificantMomentTrigger(),
            PerspectiveConflictTrigger(margin_threshold=config.get("perspective_conflict_margin_threshold", 2.0)),
        ])
        self.personality_redistill_journal_interval = config.get("personality_redistill_journal_interval", 3)
        self._personality_journal_writes_since_redistill: int = 0

        # Observer / Event Hooks
        self.on_pipeline_image: EventHook = EventHook("on_pipeline_image")
        self.on_debug_overlay: EventHook = EventHook("on_debug_overlay")
        self.on_status_update: EventHook = EventHook("on_status_update")
        self.on_state_summary: EventHook = EventHook("on_state_summary")
        self.on_prompt_update: EventHook = EventHook("on_prompt_update")
        self.on_feedback: EventHook = EventHook("on_feedback")
        self.on_chat_message: EventHook = EventHook("on_chat_message")
        self.on_eta_ready: EventHook = EventHook("on_eta_ready")
        self.on_connection_status: EventHook = EventHook("on_connection_status")
        self.on_medium_term: EventHook = EventHook("on_medium_term")
        self.on_personality_state: EventHook = EventHook("on_personality_state")
        self.on_strategic_memory: EventHook = EventHook("on_strategic_memory")
        self.on_ocr_result: EventHook = EventHook("on_ocr_result")
        self.on_scribe_output: EventHook = EventHook("on_scribe_output")
        self.on_ally_output: EventHook = EventHook("on_ally_output")
        self.on_analysis_stream_begin: EventHook = EventHook("on_analysis_stream_begin")
        self.on_analysis_stream_chunk: EventHook = EventHook("on_analysis_stream_chunk")
        self.on_analysis_stream_reset: EventHook = EventHook("on_analysis_stream_reset")
        self.on_analysis_stream_finalize: EventHook = EventHook("on_analysis_stream_finalize")
        self.on_chat_stream_begin: EventHook = EventHook("on_chat_stream_begin")
        self.on_chat_stream_chunk: EventHook = EventHook("on_chat_stream_chunk")
        self.on_chat_stream_reset: EventHook = EventHook("on_chat_stream_reset")
        self.on_chat_stream_finalize: EventHook = EventHook("on_chat_stream_finalize")
        self.on_thinking_stream_begin: EventHook = EventHook("on_thinking_stream_begin")
        self.on_thinking_stream_chunk: EventHook = EventHook("on_thinking_stream_chunk")
        self.on_thinking_stream_reset: EventHook = EventHook("on_thinking_stream_reset")
        self.on_thinking_stream_finalize: EventHook = EventHook("on_thinking_stream_finalize")

    @property
    def entity_registry(self) -> Optional[EntityRegistry]:
        with self.state_lock:
            return self.registry

    @entity_registry.setter
    def entity_registry(self, value: Optional[EntityRegistry]) -> None:
        with self.state_lock:
            self.registry = value

    def push_memory_states(self) -> None:
        """Thread-safe: reads memory state and emits via EventHooks."""
        with self.state_lock:
            if self.memory_manager is not None:
                digest = self.memory_manager.get_personality_digest()
                base = self.memory_manager.get_base_personality()
                self.on_personality_state.emit(f"Archetype: {base}\n\nDigest:\n{digest}")
                
                long_term = self.memory_manager.get_long_term_summary()
                cross_session = self.memory_manager.get_cross_session_summary()
                strat_text = []
                if cross_session:
                    strat_text.append(f"Cross-Session Summary:\n{cross_session}")
                if long_term:
                    strat_text.append(f"Strategic Long-Term Overview:\n{long_term}")
                self.on_strategic_memory.emit("\n\n".join(strat_text) if strat_text else "(no strategic memory recorded yet)")

    def update_pipeline_image(self, key: str, image: Any, title: Optional[str] = None) -> None:
        if self.gui_app is not None and hasattr(self.gui_app, "update_pipeline_image"):
            self.gui_app.update_pipeline_image(key, image, title)
        else:
            self.on_pipeline_image.emit(key, image, title)

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

    @timed
    def run_turn(self, observation: RawObservation, include_ui: bool = True) -> bool:
        if observation.image is None:
            return False

        timings: dict[str, float] = {}

        self.on_pipeline_image.emit("observation", observation.image, "RGB PIL Image Observation")
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
        self.on_debug_overlay.emit(debug_frame)
        if not self.on_debug_overlay._subscribers:
            show_image(debug_frame)

        log(
            "\n--- Screen: {screen_name} (confidence={confidence:.2f}) ---",
            screen_name=observation.screen_name, confidence=observation.screen_confidence,
        )

        log("--- Scribe extracting ({mode}) ---", mode="NO_UI" if not include_ui else "UI")
        skip_scribe_reason = getattr(observation, 'skip_scribe_reason', 'none')
        skip_ally = getattr(observation, 'skip_ally', False) or skip_scribe_reason != 'none'

        screen_category = getattr(observation, 'screen_category', None)
        is_draft = getattr(observation, 'is_draft', False)

        ocr_payload = {
            "screen_name": observation.screen_name,
            "confidence": observation.screen_confidence,
            "is_draft": is_draft,
            "confirmed_facts": observation.confirmed_facts,
            "screen_category": screen_category,
            "skip_scribe_reason": skip_scribe_reason,
        }
        self.on_ocr_result.emit(ocr_payload)

        scribe_output = None
        ally_output = None
        prompt_sent_to_ally = None

        if not skip_ally:
            t0 = time.perf_counter()
            scribe_output = self.scribe.extract(observation.image, include_ui=include_ui)
            timings["scribe"] = time.perf_counter() - t0

            self.on_scribe_output.emit(scribe_output)

            if self.category_store is not None and self.collector is not None:
                self.category_store.maybe_learn(scribe_output.screen_name_guess, self.collector.config.game_id)

            if self.collector is not None and observation.bootstrap_ready:
                self.collector.bootstrap_screen(scribe_output.screen_elements, scribe_output.screen_name_guess)

            t0 = time.perf_counter()
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

                touched_entities = []
                if self.registry is not None:
                    touched_entities = self.registry.resolve_or_create(cast(Any, scribe_output.screen_elements), self.sandbox.turn)
                    entities_context = self.registry.as_context(touched_entities, max_entities=20)
                else:
                    entities_context = "(no registry)"

                elements_context = self.sandbox.as_context()
                genre_context = self.genre_tracker.as_context()
                memory_context = self.memory_manager.build_context() if self.memory_manager else "(no memory)"
                personality_context = self.memory_manager.get_personality_context() if self.memory_manager else self.ally.base_personality
            timings["entity_resolve"] = time.perf_counter() - t0

            log("\n--- Entity registry (accumulated across the run) ---")
            log("{}", entities_context)

            log(
                "\n--- Genre: {guess} (confidence={confidence:.2f}, locked={locked}) ---",
                guess=genre_estimate.guess,
                confidence=genre_estimate.confidence,
                locked=genre_estimate.locked
            )

            log("\n--- Ally (blind to the image) ---")
            t0 = time.perf_counter()
            recent_turns = self.memory_manager.get_recent_turn_texts(n=5) if self.memory_manager else []
            entity_facts = [fact for ent in touched_entities for fact in ent.facts[-3:]]
            perspective_score = self.perspective_engine.score(recent_turns, entity_facts)
            perspective_context = self.perspective_engine.as_context(perspective_score)

            prompt_sent_to_ally = f"Elements: {elements_context}\nEntities: {entities_context}\nGenre: {genre_context}\nMemory: {memory_context}\nPerspectives: {perspective_context}"
            analysis_begun = [False]
            def ensure_analysis_begun() -> None:
                if not analysis_begun[0]:
                    analysis_begun[0] = True
                    self.on_analysis_stream_begin.emit()

            ally_output = self.ally.decide_stream(
                elements_context=elements_context,
                entities_context=entities_context,
                genre_context=genre_context,
                memory_context=memory_context,
                personality=personality_context,
                perspective_context=perspective_context,
                on_chunk=lambda text: (ensure_analysis_begun(), self.on_analysis_stream_chunk.emit(text)),
                on_reset=lambda: self.on_analysis_stream_reset.emit(),
                on_thought_begin=lambda: self.on_thinking_stream_begin.emit(),
                on_thought_chunk=lambda t: self.on_thinking_stream_chunk.emit(t),
                on_thought_reset=lambda: self.on_thinking_stream_reset.emit(),
                on_thought_finalize=lambda: (self.on_thinking_stream_finalize.emit(), ensure_analysis_begun()),
            )
            ensure_analysis_begun()
            self.on_analysis_stream_finalize.emit(ally_output.analysis)
            timings["ally"] = time.perf_counter() - t0

            self.on_ally_output.emit(ally_output)

            log("\nAnalysis:\n{analysis}", analysis=ally_output.analysis)
            log("\nActions:")
            for action in ally_output.actions:
                log("  - {text}", text=action.text)
        else:
            self.on_scribe_output.emit(None)
            t0 = time.perf_counter()
            with self.state_lock:
                self.sandbox.update([], observation.confirmed_facts)
                genre_estimate = self.genre_tracker.update("unknown", 0.0)
                if self.registry is not None:
                    touched_entities = self.registry.resolve_or_create([], self.sandbox.turn)
                    entities_context = self.registry.as_context(touched_entities, max_entities=20)
                else:
                    entities_context = "(no registry)"
            timings["entity_resolve"] = time.perf_counter() - t0

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
            self.on_ally_output.emit(ally_output)
            self.on_thinking_stream_begin.emit()
            self.on_thinking_stream_finalize.emit()
            self.on_analysis_stream_begin.emit()
            self.on_analysis_stream_chunk.emit(ally_output.analysis)
            self.on_analysis_stream_finalize.emit(ally_output.analysis)

        run_ended = False
        t0 = time.perf_counter()
        with self.state_lock:
            if self.memory_manager is not None and skip_scribe_reason != "off_game":
                self.memory_manager.record_turn(
                    self.sandbox.turn,
                    ally_output.analysis if not skip_ally else f"skip_ally: {reason_label}",
                    importance=8 if (not skip_ally and ally_output.significant_moment) else 0,
                )

                if not skip_ally:
                    personality_trigger_context: dict[str, Any] = {
                        "turn": self.sandbox.turn,
                        "importance": 8 if ally_output.significant_moment else 0,
                        "significant_moment": ally_output.significant_moment,
                        "perspective_conflict_margin": perspective_score.conflict_margin,
                    }
                    if self.personality_flush_trigger.should_trigger(personality_trigger_context):
                        self.memory_manager.add_personality_journal_entry(ally_output.analysis)
                        self._personality_journal_writes_since_redistill += 1
                        if self._personality_journal_writes_since_redistill >= self.personality_redistill_journal_interval:
                            self.memory_manager.redistill_personality()
                            self._personality_journal_writes_since_redistill = 0

            run_ended = resolve_run_ended(observation, ally_output)
            if run_ended:
                log("\n--- Run ended (boundary resolved) ---")
                if self.memory_manager is not None:
                    if self._personality_journal_writes_since_redistill > 0:
                        self.memory_manager.redistill_personality()
                        self._personality_journal_writes_since_redistill = 0
                    self.memory_manager.close_run()
                self.on_chat_message.emit("coach", "Run ended! Closing session and saving cross-session memories.")
        timings["memory_record"] = time.perf_counter() - t0

        # Emit status updates (these callbacks may access state, so we snapshot what we need)
        screen_name_snapshot = observation.screen_name
        sandbox_context_snapshot = self.sandbox.as_context()
        analysis_snapshot = ally_output.analysis
        
        self.on_status_update.emit(screen_name_snapshot, "turn")
        self.on_state_summary.emit(sandbox_context_snapshot)
        self.on_prompt_update.emit(sandbox_context_snapshot[:300])
        self.on_feedback.emit(analysis_snapshot)
        self.push_memory_states()
        self.on_eta_ready.emit()

        trace = TurnTrace(
            turn=self.sandbox.turn,
            timestamp=time.time(),
            screen_name=observation.screen_name,
            screen_confidence=observation.screen_confidence,
            is_draft_match=is_draft,
            skip_scribe_reason=skip_scribe_reason,
            skip_ally=skip_ally,
            screen_category=screen_category,
            confirmed_facts=list(observation.confirmed_facts),
            scribe_output=scribe_output,
            ally_output=ally_output,
            prompt_sent_to_ally=prompt_sent_to_ally,
            timings=timings,
        )
        self.turn_traces.append(trace)

        return run_ended

    @timed
    def run_loop(self, interval_seconds: float = TURN_INTERVAL_SECONDS) -> None:
        """Main turn loop - captures observations and processes turns.
        
        Thread-safe: coordinates with initialize_run via _initialized flag.
        """
        # Wait for initialization to complete if not already done
        # This prevents race conditions when run_loop starts before initialize_run finishes
        if not self._initialized:
            with self._initialization_lock:
                if not self._initialized:
                    log("Waiting for initialization to complete before starting run_loop...")
                    # This will be set by initialize_run
                    pass
        
        if self.collector is None:
            log("No collector configured for run_loop.")
            return

        log("Starting turn loop (every {interval_seconds}s). Ctrl+C to stop.", interval_seconds=interval_seconds)
        
        with self.state_lock:
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
                    if ended:
                        with self.state_lock:
                            if self.memory_manager is not None and self.registry is not None:
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
        """Thread-safe stop: sets running flag and closes memory manager."""
        with self.state_lock:
            self.running = False
            try:
                if self.memory_manager is not None:
                    self.memory_manager.close_run()
            except Exception as e:
                log("Failed to close memory manager during stop: {error}", error=str(e), level="warning")

    def send_message(self, text: str, message_type: str = "chat") -> None:
        """Asynchronously handles chat messages and feedback submissions from the frontend.
        
        Thread-safe: all state access is protected by state_lock.
        """
        def _handle() -> None:
            memory_context = ""
            personality_context = ""
            entities_context = "(no known entities yet)"
            elements_context = ""
            genre_context = ""
            not_started = False
            sandbox_turn = 0

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
                        sandbox_turn = self.sandbox.turn
                    else:
                        self.memory_manager.personality.record_reflection(f"Player feedback: {text}")

            if not_started:
                self.on_chat_message.emit("coach", "Game loop hasn't started yet. Hang tight!")
                return

            if message_type == "feedback":
                self.on_chat_message.emit("coach", "Got it! I've noted that feedback and adjusted my approach.")
                return

            try:
                chat_begun = [False]
                def ensure_chat_begun() -> None:
                    if not chat_begun[0]:
                        chat_begun[0] = True
                        self.on_chat_stream_begin.emit()

                res = self.ally.chat_stream(
                    elements_context=elements_context,
                    entities_context=entities_context,
                    genre_context=genre_context,
                    memory_context=memory_context,
                    personality=personality_context,
                    question=text,
                    on_chunk=lambda t: (ensure_chat_begun(), self.on_chat_stream_chunk.emit(t)),
                    on_reset=lambda: self.on_chat_stream_reset.emit(),
                    on_thought_begin=lambda: self.on_thinking_stream_begin.emit(),
                    on_thought_chunk=lambda t: self.on_thinking_stream_chunk.emit(t),
                    on_thought_reset=lambda: self.on_thinking_stream_reset.emit(),
                    on_thought_finalize=lambda: (self.on_thinking_stream_finalize.emit(), ensure_chat_begun()),
                )
                ensure_chat_begun()
                with self.state_lock:
                    if self.memory_manager is not None:
                        self.memory_manager.record_turn(
                            sandbox_turn,
                            f"Player asked: '{text}' -> Ally answered: '{res.response}'",
                            importance=5
                        )
                self.on_chat_stream_finalize.emit(res.response)
            except Exception as e:
                self.on_chat_stream_reset.emit()
                self.on_chat_stream_finalize.emit(f"(Error: {e})")

        threading.Thread(target=_handle, daemon=True).start()

    def initialize_run(self) -> None:
        """Initializes memory manager, registry, and collector based on provided args/config.
        
        Thread-safe: uses initialization lock to prevent race conditions during
        startup when multiple threads might call this simultaneously.
        """
        # Use a separate initialization lock to avoid deadlocks with state_lock
        # (state_lock might be held by run_loop while initialize_run is called)
        with self._initialization_lock:
            log("Initializing run in AllyCore...")
            if self._initialized:
                return  # Already initialized
            
            player_id = DEFAULT_PLAYER_ID
            if self.image_path:
                save_id, _ = self.save_tracker.resolve_save_id(player_id=player_id, game_id=ADHOC_IMAGE_GAME_ID)
                self.memory_manager = MemoryManager(
                    player_id=player_id,
                    game_id=ADHOC_IMAGE_GAME_ID,
                    save_id=save_id,
                    provider=self.provider,
                    base_personality=self.ally.base_personality,
                    save_tracker=self.save_tracker,
                )
                self.registry = EntityRegistry(
                    player_id=player_id,
                    game_id=ADHOC_IMAGE_GAME_ID,
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
            
            self._initialized = True
