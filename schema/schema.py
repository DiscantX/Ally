"""Structured output schemas shared between the Scribe and Ally.

Keeping these in one place means both agents agree on the shape of a
screen element without importing each other's modules.
"""

from pydantic import BaseModel


class ScreenElement(BaseModel):
    id: str
    label: str
    description: str
    box_2d: list[int]  # [y_min, x_min, y_max, x_max], normalized 0-1000


class ScribeOutput(BaseModel):
    screen_elements: list[ScreenElement]
    genre_guess: str
    genre_confidence: float  # 0.0-1.0, the Scribe's own confidence in genre_guess


class ActionItem(BaseModel):
    action_id: str
    text: str  # e.g. "Click the [flower pot]"
    target_entity_ids: list[str]


class AllyOutput(BaseModel):
    analysis: str
    actions: list[ActionItem]
