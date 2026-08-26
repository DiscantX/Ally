"""Structured output schemas shared between the Scribe and Ally.

Keeping these in one place means both agents agree on the shape of a
screen element without importing each other's modules.
"""

from typing import Literal
from pydantic import BaseModel, Field


class ScreenElement(BaseModel):
    id: str
    label: str
    description: str
    box_2d: list[int]  # [y_min, x_min, y_max, x_max], normalized 0-1000
    is_decorative: bool = False


class ScribeOutput(BaseModel):
    screen_elements: list[ScreenElement]
    genre_guess: str
    genre_confidence: float
    screen_name_guess: str  # short functional label, e.g. "combat", "map", "shop"


class ActionItem(BaseModel):
    action_id: str
    text: str  # e.g. "Click the [flower pot]"
    target_entity_ids: list[str]


class AllyOutput(BaseModel):
    analysis: str = Field(
        description="The exact direct spoken dialogue that Ally speaks out loud to the player in first/second person ('you', 'we'). MUST NOT be internal meta-thoughts, plans, or third-person summaries."
    )
    actions: list[ActionItem]
    run_boundary: Literal["none", "run_ended"] = "none"


class AllyChatOutput(BaseModel):
    response: str

