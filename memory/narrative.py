"""Tiered Narrative Memory Manager.
Manages short-term rolling buffer, medium-term situational summaries,
and long-term strategic summaries with LLM compression and database persistence.
"""

from collections import deque
from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel

from llm.gemini_provider import GeminiProvider
from memory.db import MemoryDB
from memory.triggers import Trigger, TurnCountTrigger
from prompts.narrative import NARRATIVE_MEDIUM_TERM_PROMPT, NARRATIVE_LONG_TERM_PROMPT


class TextSummary(BaseModel):
    summary: str


@dataclass
class ShortTermEntry:
    turn: int
    summary: str


class NarrativeMemoryManager:
    def __init__(
        self,
        player_id: str,
        game_id: str,
        save_id: str,
        provider: GeminiProvider,
        db: MemoryDB,
        short_term_capacity: int = 8,
        flush_trigger: Trigger | None = None,
    ):
        self.player_id = player_id
        self.game_id = game_id
        self.save_id = save_id
        self.provider = provider
        self.db = db
        self.short_term_capacity = short_term_capacity
        self._short_term: deque[ShortTermEntry] = deque(maxlen=short_term_capacity)
        self.flush_trigger = flush_trigger or TurnCountTrigger(interval=short_term_capacity)
        self._medium_term_summaries: list[str] = []
        self._long_term_summary: str = ""
        self._load_from_db()

    def _load_from_db(self) -> None:
        short_rows = self.db.get_narrative_entries(self.player_id, self.game_id, self.save_id, "short")
        for row in short_rows:
            self._short_term.append(ShortTermEntry(turn=row["turn"], summary=row["summary"]))
        
        med_rows = self.db.get_narrative_entries(self.player_id, self.game_id, self.save_id, "medium")
        self._medium_term_summaries = [row["summary"] for row in med_rows]

        long_rows = self.db.get_narrative_entries(self.player_id, self.game_id, self.save_id, "long")
        if long_rows:
            self._long_term_summary = long_rows[-1]["summary"]

    def record_turn(self, turn: int, ally_analysis: str, importance: int = 0, explicit_checkpoint: bool = False) -> None:
        entry = ShortTermEntry(turn=turn, summary=ally_analysis)
        self._short_term.append(entry)
        self.db.save_narrative_entry(self.player_id, self.game_id, self.save_id, turn, "short", ally_analysis)

        context = {"turn": turn, "importance": importance, "explicit_checkpoint": explicit_checkpoint}
        if self.flush_trigger.should_trigger(context):
            self._flush_to_medium_term()

    def build_context(self) -> str:
        parts = []
        if self._long_term_summary:
            parts.append(f"Strategic Long-Term Overview:\n{self._long_term_summary}")
        if self._medium_term_summaries:
            parts.append("Recent Situational Summaries:\n" + "\n".join([f"- {s}" for s in self._medium_term_summaries[-3:]]))
        if self._short_term:
            lines = [f"- (turn {e.turn}) {e.summary}" for e in self._short_term]
            parts.append("Recent Turns:\n" + "\n".join(lines))
        
        if not parts:
            return "(no memory yet -- this is the first turn)"
        return "\n\n".join(parts)

    def _flush_to_medium_term(self) -> None:
        if not self._short_term:
            return
        buffer_text = "\n".join([f"Turn {e.turn}: {e.summary}" for e in self._short_term])
        prompt = NARRATIVE_MEDIUM_TERM_PROMPT.format(buffer_text=buffer_text)
        try:
            result = self.provider.generate_structured(
                model="gemini-3.5-flash-lite",
                contents=[prompt],
                schema=TextSummary,
            )
            summary = result.summary
        except Exception:
            summary = f"Summary of turns {[e.turn for e in self._short_term]}: gameplay progress recorded."

        self._medium_term_summaries.append(summary.strip())
        latest_turn = self._short_term[-1].turn
        self.db.save_narrative_entry(self.player_id, self.game_id, self.save_id, latest_turn, "medium", summary.strip())

    def flush_to_long_term(self) -> None:
        if not self._medium_term_summaries:
            return
        med_text = "\n".join(self._medium_term_summaries)
        prompt = NARRATIVE_LONG_TERM_PROMPT.format(med_text=med_text)
        try:
            result = self.provider.generate_structured(
                model="gemini-3.5-flash-lite",
                contents=[prompt],
                schema=TextSummary,
            )
            summary = result.summary
        except Exception:
            summary = "Long-term playthrough progress synthesized."

        self._long_term_summary = summary.strip()
        latest_turn = self._short_term[-1].turn if self._short_term else 0
        self.db.save_narrative_entry(self.player_id, self.game_id, self.save_id, latest_turn, "long", summary.strip())

    def flush_to_cross_session(self) -> None:
        self.flush_to_long_term()
