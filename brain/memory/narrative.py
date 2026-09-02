"""Tiered Narrative Memory Manager.
Manages short-term rolling buffer, medium-term situational summaries,
and long-term strategic summaries with LLM compression and database persistence.
"""

from collections import deque
from dataclasses import dataclass
from typing import Any
import threading
from pydantic import BaseModel

from infrastructure.llm.providers.gemini_provider import GeminiProvider
from brain.memory.db import MemoryDB
from brain.memory.triggers import Trigger, TurnCountTrigger, CompositeTrigger, SalienceEventTrigger, ExplicitAllyTrigger
from brain.knowledge.prompts.narrative import NARRATIVE_MEDIUM_TERM_PROMPT, NARRATIVE_LONG_TERM_PROMPT, CROSS_SESSION_SUMMARY_PROMPT
from cabinet.configs.config_manager import load_user_config, get_model, get_thinking_level


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
        short_term_capacity: int | None = None,
        medium_flush_interval: int = 8,
        flush_trigger: Trigger | None = None,
        model: str | None = None,
        save_tracker: Any | None = None,
    ):
        if not isinstance(player_id, str) or not player_id.strip():
            raise ValueError(f"player_id must be a non-empty string, got: {player_id!r}")
        if not isinstance(game_id, str) or not game_id.strip():
            raise ValueError(f"game_id must be a non-empty string, got: {game_id!r}")
        if not isinstance(save_id, str) or not save_id.strip():
            raise ValueError(f"save_id must be a non-empty string, got: {save_id!r}")
        if provider is None:
            raise ValueError("provider must not be None")
        if db is None:
            raise ValueError("db must not be None")
        
        config = load_user_config()
        self.player_id = player_id
        self.game_id = game_id
        self.save_id = save_id
        self.provider = provider
        self.db = db
        self.short_term_capacity = short_term_capacity or config["short_term_capacity"]
        self.medium_flush_interval = medium_flush_interval
        self.model = model or get_model("narrative_model", config)
        self.thinking_level = get_thinking_level("narrative", config)
        self.save_tracker = save_tracker
        self._lock = threading.RLock()
        self._short_term: deque[ShortTermEntry] = deque(maxlen=short_term_capacity)
        self.flush_trigger = flush_trigger or CompositeTrigger([
            TurnCountTrigger(interval=medium_flush_interval),
            SalienceEventTrigger(importance_threshold=8),
            ExplicitAllyTrigger()
        ])
        self._medium_term_summaries: list[str] = []
        self._long_term_summary: str = ""
        self._entry_count = 0
        self._load_from_db()

    def _load_from_db(self) -> None:
        with self._lock:
            short_rows = self.db.get_narrative_entries(self.player_id, self.game_id, self.save_id, "short")
            for row in short_rows:
                self._short_term.append(ShortTermEntry(turn=row["turn"], summary=row["summary"]))
            self._entry_count = len(short_rows)
            
            med_rows = self.db.get_narrative_entries(self.player_id, self.game_id, self.save_id, "medium")
            self._medium_term_summaries = [row["summary"] for row in med_rows]

            long_rows = self.db.get_narrative_entries(self.player_id, self.game_id, self.save_id, "long")
            if long_rows:
                self._long_term_summary = long_rows[-1]["summary"]

    def record_turn(self, turn: int, ally_analysis: str, importance: int = 0, explicit_checkpoint: bool = False) -> None:
        with self._lock:
            self._entry_count += 1
            entry = ShortTermEntry(turn=turn, summary=ally_analysis)
            self._short_term.append(entry)
            self.db.save_narrative_entry(self.player_id, self.game_id, self.save_id, turn, "short", ally_analysis)

            if self.save_tracker:
                self.save_tracker.touch(self.player_id, self.game_id, self.save_id)

            context = {"turn": self._entry_count, "importance": importance, "explicit_checkpoint": explicit_checkpoint}
            if self.flush_trigger.should_trigger(context):
                self._flush_to_medium_term()

    def get_recent_turn_texts(self, n: int = 5) -> list[str]:
        """Plain summary strings from the short-term buffer, most recent
        last -- for consumers that need raw text rather than the formatted
        [`build_context()`](brain/memory/narrative.py) blob (e.g. [`PerspectiveEngine`](brain/reasoning/perspective_engine.py)).
        
        Thread-safe: uses lock to protect access to _short_term.
        """
        with self._lock:
            return [entry.summary for entry in list(self._short_term)[-n:]]

    def build_context(self) -> str:
        """Thread-safe: uses lock to protect access to shared state."""
        with self._lock:
            parts = []
            cross_record = self.db.get_latest_cross_session(self.player_id, self.game_id)
        if cross_record:
            parts.append(f"Cross-Session Game Summary:\n{cross_record['summary']}")
        if self._long_term_summary:
            parts.append(f"Strategic Long-Term Overview:\n{self._long_term_summary}")
        if self._medium_term_summaries:
            parts.append("Recent Situational Summaries:\n" + "\n".join([f"- {s}" for s in self._medium_term_summaries[-3:]]))
        if self._short_term:
            # If we have more entries than capacity, summarize the oldest
            if self._entry_count > self.short_term_capacity:
                # Calculate how many entries to show directly
                entries_to_show = min(self.short_term_capacity - 1, len(self._short_term))
                shown_entries = list(self._short_term)[-entries_to_show:]
                oldest_turn = shown_entries[0].turn
                dropped_count = self._entry_count - self.short_term_capacity
                lines = [f"- (turn {e.turn}) {e.summary}" for e in shown_entries]
                lines.append(f"- ...and {dropped_count} earlier turns (summarized)")
                parts.append("Recent Turns:\n" + "\n".join(lines))
            else:
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
                model=self.model,
                contents=[prompt],
                schema=TextSummary,
                thinking_level=self.thinking_level,
            )
            summary = result.summary
        except Exception as e:
            log("Failed to generate medium-term summary: {error}", error=str(e), level="warning")
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
                model=self.model,
                contents=[prompt],
                schema=TextSummary,
                thinking_level=self.thinking_level,
            )
            summary = result.summary
        except Exception as e:
            log("Failed to generate long-term summary: {error}", error=str(e), level="warning")
            summary = "Long-term playthrough progress synthesized."

        self._long_term_summary = summary.strip()
        latest_turn = self._short_term[-1].turn if self._short_term else 0
        self.db.save_narrative_entry(self.player_id, self.game_id, self.save_id, latest_turn, "long", summary.strip())

    def close_run(self) -> None:
        if not self._long_term_summary:
            if self._medium_term_summaries:
                self.flush_to_long_term()
            elif self._short_term:
                self._flush_to_medium_term()
                self.flush_to_long_term()
            else:
                self._long_term_summary = "Run completed with no recorded turns."

        just_finished_run = self._long_term_summary
        prior_record = self.db.get_latest_cross_session(self.player_id, self.game_id)
        prior_cross_session = prior_record["summary"] if prior_record else "This is the first recorded run for this game."

        prompt = CROSS_SESSION_SUMMARY_PROMPT.format(
            prior_cross_session=prior_cross_session,
            just_finished_run=just_finished_run,
        )
        try:
            result = self.provider.generate_structured(
                model=self.model,
                contents=[prompt],
                schema=TextSummary,
                thinking_level=self.thinking_level,
            )
            new_summary = result.summary
        except Exception as e:
            log("Failed to generate cross-session summary: {error}", error=str(e), level="warning")
            new_summary = f"Cross-session summary synthesized from run {self.save_id}."

        self.db.insert_cross_session(self.player_id, self.game_id, new_summary.strip(), self.save_id)

        if self.save_tracker:
            self.save_tracker.close(self.player_id, self.game_id, self.save_id)

    def flush_to_cross_session(self) -> None:
        self.close_run()
