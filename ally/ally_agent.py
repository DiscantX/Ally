"""Agent B: Ally.

This is the "Blind Brain." Ally never receives the screenshot -- only the
State Sandbox's text summary and the Entity Registry's context. That's the
whole point of the air-gap: even if the underlying model has memorized a
walkthrough of this game, Ally is only ever handed facts your own pipeline
extracted this run, so it has nothing else to reason from.

Personality and long-term memory are not wired in yet -- this is the seam
where the MemoryManager.build_context() from the earlier design plugs in.
For now PERSONALITIES stands in for that.
"""

from llm.gemini_provider import GeminiProvider
from schema.schema import AllyOutput
from ally.personalities import PERSONALITIES

ALLY_MODEL = "gemini-3.5-flash-lite"

ALLY_PROMPT_TEMPLATE = (
    "You are Ally, a companion experiencing the game right alongside the human player. "
    "{personality}\n\n"
    "Keep the focus entirely on the two of you — speak directly to 'you' and refer to your "
    "joint adventures as 'we'. "
    "You have never seen this game before and have no access to the raw "
    "screen image -- you only know what's below, extracted this run.\n\n"
    "Best guess at genre so far: {genre}\n\n"
    "Current screen elements:\n{elements}\n\n"
    "Known entities so far (persist across the whole run):\n{entities}\n\n"
    "Write a short analysis (3-4 sentences) of what's happening and what "
    "the player should consider doing next, from a strategic point of "
    "view. Then list a few specific candidate actions, e.g. 'Click the "
    "[flower pot]', wrapping nouns in square brackets and referencing only "
    "the screen element ids given above in target_entity_ids."
)

class Ally:
    def __init__(self, provider: GeminiProvider, base_personality: str = PERSONALITIES["Scout"]):
        self.provider = provider
        self.base_personality = base_personality

    def decide(
        self,
        elements_context: str,
        entities_context: str,
        genre_context: str, 
        personality: str | None = None
    ) -> AllyOutput:
        prompt = ALLY_PROMPT_TEMPLATE.format(
            personality=personality if personality else self.base_personality,
            genre=genre_context,
            elements=elements_context,
            entities=entities_context,
        )
        return self.provider.generate_structured(
            model=ALLY_MODEL,
            contents=[prompt],
            schema=AllyOutput,
        )
