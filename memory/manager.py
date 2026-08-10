"""Memory Manager: the seam ally/ally_agent.py's PERSONALITY_STUB comment
anticipates -- this is where Ally's cross-turn memory will eventually
come from.

Per the decision log, the target design is a tiered, lossy compression
pipeline:

    Short-term (rolling buffer)
      -> Medium-term (situational summary)
        -> Long-term (strategic summary, this run)
          -> Cross-session summary (on run close)

This is a vertical slice, not the full system: only the short-term tier
is real. It's a bounded rolling buffer of recent turns, fed back into
Ally's prompt every turn. The medium/long/cross-session tiers are
stubbed -- present as real methods with real call sites wired in (see
_maybe_flush_to_medium_term below, called from record_turn), so the seam
is provable rather than just a comment, but they don't do any LLM-based
compression yet.

Known compromise, flagged rather than hidden: a real short-term buffer
should flush into a compressed medium-term summary via an LLM call when
it fills, per the decision log ("each tier is populated by an LLM
summarization call from the tier below it -- nothing skips a tier").
That call isn't built yet, so for now the buffer is just a bounded
deque: the oldest entry silently falls off once at capacity. That's
lossy in an *unintended* way (arbitrary truncation, not summarization)
until flush_to_medium_term's TODO is implemented.

Scoping: per the decision log, run-specific narrative memory is keyed by
(player_id, game_id, save_id) -- personality and player-relationship
memory are a separate, player_id-only system this class does NOT hold
(see ally/personalities.py). All three keys are threaded through now,
even though this vertical slice only ever runs one save at a time, so
wiring up real cross-run persistence later doesn't require touching
call sites.
"""

from collections import deque
from dataclasses import dataclass


@dataclass
class ShortTermEntry:
    turn: int
    summary: str
    # NOTE: currently Ally's own `analysis` text, verbatim -- see
    # record_turn(). The design doc's short-term tier examples are
    # terse factual sentences ("We just tried to open the door."), not
    # full personality-flavored prose. Feeding Ally's own flavored
    # analysis back into its own next prompt is a plausible mechanism
    # for personality dominance to *compound* turn over turn rather than
    # dilute -- watch for this in playtesting. The real fix is a small
    # distillation step here (strip flavor, keep facts) before this
    # entry is created, once that's worth building.


class MemoryManager:
    def __init__(
        self,
        player_id: str,
        game_id: str,
        save_id: str,
        short_term_capacity: int = 8,
    ):
        self.player_id = player_id
        self.game_id = game_id
        self.save_id = save_id
        self.short_term_capacity = short_term_capacity
        self._short_term: deque[ShortTermEntry] = deque(maxlen=short_term_capacity)

    def record_turn(self, turn: int, ally_analysis: str) -> None:
        """Call once per turn, after Ally responds."""
        self._short_term.append(ShortTermEntry(turn=turn, summary=ally_analysis))
        self._maybe_flush_to_medium_term()

    def build_context(self) -> str:
        """Compact text form for injecting into Ally's prompt. This is the
        short-term-tier half of the eventual full MemoryManager context;
        personality/player-relationship memory merges in here too once
        that system exists, alongside medium/long-term summaries once
        those tiers are real."""
        if not self._short_term:
            return "(no memory yet -- this is the first turn)"
        lines = [f"- (turn {e.turn}) {e.summary}" for e in self._short_term]
        return "\n".join(lines)

    def _maybe_flush_to_medium_term(self) -> None:
        """Stub. Real implementation: once short-term hits capacity (or a
        time-based fallback fires, per the decision log), summarize the
        buffer into a 2-3 sentence medium-term situational summary via an
        LLM call -- structurally the same shape as Scribe.extract() or
        Ally.decide(), just a third `generate_structured` caller. Not
        implemented yet; this vertical slice only proves out the
        short-term tier and this call site."""
        pass

    def flush_to_long_term(self) -> None:
        """Stub. Per the decision log: triggered by narrative beats
        (location change, major state change) with a time-based
        fallback. No call site wired up yet -- there's no location/state-
        change detection to trigger it from in this slice."""
        pass

    def flush_to_cross_session(self) -> None:
        """Stub. Triggered on run end. Call site is wired in main.py's
        shutdown path so the seam exists even though this is a no-op."""
        pass