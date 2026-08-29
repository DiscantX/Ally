"""Pluggable trigger mechanisms for narrative memory compression and personality reflection.
Supports turn count thresholds, event/salience triggers, and explicit Ally triggers.
"""

from abc import ABC, abstractmethod
from typing import Any

class Trigger(ABC):
    @abstractmethod
    def should_trigger(self, context: dict[str, Any]) -> bool:
        """Evaluate whether the trigger condition is met."""
        pass


class TurnCountTrigger(Trigger):
    def __init__(self, interval: int = 8):
        self.interval = interval
        self._turns_since_flush = 0

    def should_trigger(self, context: dict[str, Any]) -> bool:
        turn = context.get("turn", 0)
        # Trigger every `interval` turns
        if turn > 0 and turn % self.interval == 0:
            return True
        return False


class SalienceEventTrigger(Trigger):
    def __init__(self, importance_threshold: int = 8):
        self.importance_threshold = importance_threshold

    def should_trigger(self, context: dict[str, Any]) -> bool:
        importance = context.get("importance", 0)
        return importance >= self.importance_threshold


class ExplicitAllyTrigger(Trigger):
    def should_trigger(self, context: dict[str, Any]) -> bool:
        return bool(context.get("explicit_checkpoint", False))


class SignificantMomentTrigger(Trigger):
    def should_trigger(self, context: dict[str, Any]) -> bool:
        return bool(context.get("significant_moment", False))


class PerspectiveConflictTrigger(Trigger):
    def __init__(self, margin_threshold: float = 2.0):
        self.margin_threshold = margin_threshold

    def should_trigger(self, context: dict[str, Any]) -> bool:
        margin = context.get("perspective_conflict_margin")
        if margin is None:
            return False
        return margin <= self.margin_threshold


class CompositeTrigger(Trigger):
    def __init__(self, triggers: list[Trigger]):
        self.triggers = triggers

    def should_trigger(self, context: dict[str, Any]) -> bool:
        return any(t.should_trigger(context) for t in self.triggers)


def resolve_run_ended(observation: Any, ally_output: Any) -> bool:
    """Resolves whether a run has ended based on priority:
    1. Collector native signal (`observation.run_ended`) takes absolute priority.
    2. Ally semantic output (`ally_output.run_boundary == "run_ended"`) serves as fallback.
    """
    if getattr(observation, "run_ended", False):
        return True
    if getattr(ally_output, "run_boundary", "none") == "run_ended":
        return True
    return False

