from dataclasses import dataclass, field
from typing import Any

@dataclass
class TurnTrace:
    turn: int
    timestamp: float
    screen_name: str
    screen_confidence: float
    is_draft_match: bool
    skip_scribe_reason: str
    skip_ally: bool
    screen_category: str | None
    confirmed_facts: list[Any]
    scribe_output: Any | None
    ally_output: Any | None
    prompt_sent_to_ally: str | None
    timings: dict[str, float] = field(default_factory=dict)
