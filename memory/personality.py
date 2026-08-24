"""Multi-Resolution Personality Memory Manager.
Manages Master append-only reflection journals, Digest summaries, and Micro prompt injection tiers.
"""

from typing import Any
from pydantic import BaseModel

from llm.gemini_provider import GeminiProvider
from memory.db import MemoryDB


class TextSummary(BaseModel):
    summary: str


class PersonalityMemoryManager:
    def __init__(self, player_id: str, provider: GeminiProvider, db: MemoryDB, base_personality: str):
        self.player_id = player_id
        self.provider = provider
        self.db = db
        self.base_personality = base_personality
        self._master_journal: list[str] = []
        self._digest: str = ""
        self._micro: str = ""
        self._load_from_db()

    def _load_from_db(self) -> None:
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

    def record_reflection(self, reflection_text: str) -> None:
        self._master_journal.append(reflection_text)
        self.db.save_personality_entry(self.player_id, "master", reflection_text)
        self.redistill()

    def redistill(self) -> None:
        """Regenerate Digest and Micro personality tiers from the Master journal."""
        if not self._master_journal:
            self._digest = self.base_personality
            self._micro = self.base_personality
            return

        journal_text = "\n".join(self._master_journal)
        
        digest_prompt = (
            "Based on the following master reflection journal of our companion Ally, "
            "synthesize a comprehensive personality digest (200-400 words) capturing tone, "
            "quirks, and player relationship dynamics:\n\n"
            f"{journal_text}"
        )
        try:
            digest_res = self.provider.generate_structured(
                model="gemini-3.5-flash-lite",
                contents=[digest_prompt],
                schema=TextSummary,
            )
            self._digest = digest_res.summary.strip()
        except Exception:
            self._digest = self.base_personality

        micro_prompt = (
            "Boil down the following personality digest into an ultra-concise micro prompt (< 50 tokens) "
            "suitable for direct injection into a prompt to maintain voice consistency:\n\n"
            f"{self._digest}"
        )
        try:
            micro_res = self.provider.generate_structured(
                model="gemini-3.5-flash-lite",
                contents=[micro_prompt],
                schema=TextSummary,
            )
            self._micro = micro_res.summary.strip()
        except Exception:
            self._micro = self.base_personality

        self.db.save_personality_entry(self.player_id, "digest", self._digest)
        self.db.save_personality_entry(self.player_id, "micro", self._micro)

    def get_prompt_context(self) -> str:
        return self._micro if self._micro else self.base_personality
