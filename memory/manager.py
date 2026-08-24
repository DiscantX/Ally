"""Master Memory System Coordinator.
Unifies NarrativeMemoryManager, PersonalityMemoryManager, and MemoryDB under a single clean interface
drop-in compatible with the existing MemoryManager class.
"""

from typing import Any
from llm.gemini_provider import GeminiProvider
from memory.db import MemoryDB
from memory.narrative import NarrativeMemoryManager
from memory.personality import PersonalityMemoryManager
from memory.triggers import Trigger, TurnCountTrigger


class MemorySystem:
    def __init__(
        self,
        player_id: str,
        game_id: str,
        save_id: str,
        provider: GeminiProvider,
        base_personality: str,
        short_term_capacity: int = 8,
        flush_trigger: Trigger | None = None,
        db_path: str = "state/memory.db",
    ):
        self.player_id = player_id
        self.game_id = game_id
        self.save_id = save_id
        self.db = MemoryDB(db_path)
        
        self.narrative = NarrativeMemoryManager(
            player_id=player_id,
            game_id=game_id,
            save_id=save_id,
            provider=provider,
            db=self.db,
            short_term_capacity=short_term_capacity,
            flush_trigger=flush_trigger,
        )
        self.personality = PersonalityMemoryManager(
            player_id=player_id,
            provider=provider,
            db=self.db,
            base_personality=base_personality,
        )

    def record_turn(self, turn: int, ally_analysis: str, importance: int = 0, explicit_checkpoint: bool = False) -> None:
        self.narrative.record_turn(turn, ally_analysis, importance=importance, explicit_checkpoint=explicit_checkpoint)

    def build_context(self) -> str:
        return self.narrative.build_context()

    def get_personality_context(self) -> str:
        return self.personality.get_prompt_context()

    def flush_to_cross_session(self) -> None:
        self.narrative.flush_to_cross_session()


# Drop-in alias for backwards compatibility
MemoryManager = MemorySystem
