"""Master Memory System Coordinator.
Unifies NarrativeMemoryManager, PersonalityMemoryManager, and MemoryDB under a single clean interface
drop-in compatible with the existing MemoryManager class.
"""

from typing import Any
import threading
from infrastructure.logger import log
from infrastructure.llm.providers.gemini_provider import GeminiProvider
from brain.constants import DEFAULT_MEDIUM_FLUSH_INTERVAL, DEFAULT_SHORT_TERM_CAPACITY
from brain.memory.db import MemoryDB
from brain.memory.narrative import NarrativeMemoryManager
from brain.memory.personality import PersonalityMemoryManager
from brain.memory.triggers import Trigger, TurnCountTrigger
from brain.memory.save_tracker import SaveTracker


class MemorySystem:
    def __init__(
        self,
        player_id: str,
        game_id: str,
        save_id: str,
        provider: GeminiProvider,
        base_personality: str,
        short_term_capacity: int = DEFAULT_SHORT_TERM_CAPACITY,
        medium_flush_interval: int = DEFAULT_MEDIUM_FLUSH_INTERVAL,
        flush_trigger: Trigger | None = None,
        db_path: str | None = None,
        save_tracker: SaveTracker | None = None,
    ) -> None:
        if not isinstance(player_id, str) or not player_id.strip():
            raise ValueError(f"player_id must be a non-empty string, got: {player_id!r}")
        if not isinstance(game_id, str) or not game_id.strip():
            raise ValueError(f"game_id must be a non-empty string, got: {game_id!r}")
        if not isinstance(save_id, str) or not save_id.strip():
            raise ValueError(f"save_id must be a non-empty string, got: {save_id!r}")
        if provider is None:
            raise ValueError("provider must not be None")
        if not isinstance(base_personality, str) or not base_personality.strip():
            raise ValueError(f"base_personality must be a non-empty string, got: {base_personality!r}")
        
        log("Initializing MemorySystem (MemoryManager)...")
        self.lock = threading.Lock()
        self.player_id = player_id
        self.game_id = game_id
        self.save_id = save_id
        self.db = MemoryDB(db_path=db_path, player_id=player_id)
        self.save_tracker = save_tracker or SaveTracker(self.db)
        
        self.narrative = NarrativeMemoryManager(
            player_id=player_id,
            game_id=game_id,
            save_id=save_id,
            provider=provider,
            db=self.db,
            short_term_capacity=short_term_capacity,
            medium_flush_interval=medium_flush_interval,
            flush_trigger=flush_trigger,
            save_tracker=self.save_tracker,
        )
        self.personality = PersonalityMemoryManager(
            player_id=player_id,
            provider=provider,
            db=self.db,
            base_personality=base_personality,
        )

    def record_turn(self, turn: int, ally_analysis: str, importance: int = 0, explicit_checkpoint: bool = False) -> None:
        with self.lock:
            self.narrative.record_turn(turn, ally_analysis, importance=importance, explicit_checkpoint=explicit_checkpoint)

    def build_context(self) -> str:
        with self.lock:
            return self.narrative.build_context()

    def get_recent_turn_texts(self, n: int = 5) -> list[str]:
        with self.lock:
            return self.narrative.get_recent_turn_texts(n)

    def get_personality_context(self) -> str:
        with self.lock:
            return self.personality.get_prompt_context()

    def get_medium_term_summaries(self) -> list[str]:
        with self.lock:
            return list(self.narrative._medium_term_summaries)

    def get_long_term_summary(self) -> str:
        with self.lock:
            return self.narrative._long_term_summary

    def get_cross_session_summary(self) -> str:
        with self.lock:
            record = self.db.get_latest_cross_session(self.player_id, self.game_id)
            return record["summary"] if record else ""

    def get_personality_digest(self) -> str:
        with self.lock:
            return self.personality._digest or self.personality.base_personality

    def get_base_personality(self) -> str:
        with self.lock:
            return self.personality.base_personality

    def flush_to_cross_session(self) -> None:
        with self.lock:
            self.narrative.flush_to_cross_session()

    def add_personality_journal_entry(self, text: str) -> None:
        with self.lock:
            self.personality.add_journal_entry(text)

    def redistill_personality(self) -> None:
        with self.lock:
            self.personality.redistill()

    def close_run(self) -> None:
        with self.lock:
            self.narrative.close_run()


# Drop-in alias for backwards compatibility
MemoryManager = MemorySystem
