"""Multi-Resolution Personality Memory Manager.
Manages Master append-only reflection journals, Digest summaries, and Micro prompt injection tiers.
"""

from typing import Any
import threading
from pydantic import BaseModel

from infrastructure.llm.providers.gemini_provider import GeminiProvider
from brain.memory.db import MemoryDB
from brain.knowledge.prompts.personality import PERSONALITY_DIGEST_PROMPT, PERSONALITY_MICRO_PROMPT
from cabinet.configs.config_manager import load_user_config, get_model, get_thinking_level


class TextSummary(BaseModel):
    summary: str


class PersonalityMemoryManager:
    def __init__(self, player_id: str, provider: GeminiProvider, db: MemoryDB, base_personality: str, model: str | None = None, thinking_level: str | None = None):
        config = load_user_config()
        self.player_id = player_id
        self.provider = provider
        self.db = db
        self.base_personality = base_personality
        self.model = model or get_model("personality_model", config)
        self.thinking_level = thinking_level or get_thinking_level("personality", config)
        self._lock = threading.RLock()
        self._master_journal: list[str] = []
        self._digest: str = ""
        self._micro: str = ""
        self._load_from_db()

    def _load_from_db(self) -> None:
        with self._lock:
            master_rows = self.db.get_personality_entries(self.player_id, "master")
            self._master_journal = [row["content"] for row in master_rows]

            digest_rows = self.db.get_personality_entries(self.player_id, "digest")
            if digest_rows:
                self._digest = digest_rows[-1]["content"]

            micro_rows = self.db.get_personality_entries(self.player_id, "micro")
            if micro_rows:
                self._micro = micro_rows[-1]["content"]

            if not self._micro:
                self._micro = self.base_personality

    def add_journal_entry(self, text: str) -> None:
        with self._lock:
            self._master_journal.append(text)
            self.db.save_personality_entry(self.player_id, "master", text)

    def record_reflection(self, reflection_text: str) -> None:
        with self._lock:
            self.add_journal_entry(reflection_text)
            self.redistill()

    def redistill(self) -> None:
        """Regenerate Digest and Micro personality tiers from the Master journal.
        
        Thread-safe: uses lock to protect access to journal and digest/micro state.
        """
        with self._lock:
            if not self._master_journal:
                self._digest = self.base_personality
                self._micro = self.base_personality
                return

            journal_text = "\n".join(self._master_journal)
        
        digest_prompt = PERSONALITY_DIGEST_PROMPT.format(journal_text=journal_text)
        try:
            digest_res = self.provider.generate_structured(
                model=self.model,
                contents=[digest_prompt],
                schema=TextSummary,
                thinking_level=self.thinking_level,
            )
            self._digest = digest_res.summary.strip()
        except Exception as e:
            log("Failed to generate personality digest: {error}", error=str(e), level="warning")
            self._digest = self.base_personality

        micro_prompt = PERSONALITY_MICRO_PROMPT.format(digest=self._digest)
        try:
            micro_res = self.provider.generate_structured(
                model=self.model,
                contents=[micro_prompt],
                schema=TextSummary,
                thinking_level=self.thinking_level,
            )
            self._micro = micro_res.summary.strip()
        except Exception as e:
            log("Failed to generate personality micro: {error}", error=str(e), level="warning")
            self._micro = self.base_personality

        self.db.save_personality_entry(self.player_id, "digest", self._digest)
        self.db.save_personality_entry(self.player_id, "micro", self._micro)

    def get_prompt_context(self) -> str:
        """Thread-safe: uses lock to protect access to _micro."""
        with self._lock:
            return self._micro if self._micro else self.base_personality
