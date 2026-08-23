"""Agent B: Ally.

This is the "Blind Brain." Ally never receives the screenshot -- only the
State Sandbox's text summary and the Entity Registry's context. That's the
whole point of the air-gap: even if the underlying model has memorized a
walkthrough of this game, Ally is only ever handed facts your own pipeline
extracted this run, so it has nothing else to reason from.

Personality/player-relationship memory is not wired in yet -- this is the
seam where the full MemoryManager.build_context() (personality + memory
combined) from the earlier design plugs in. PERSONALITIES stands in for
the personality half; MemoryManager (memory/manager.py) now supplies the
short-term-narrative half for real, as a vertical slice.
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
    "What's happened so far this run (most recent last):\n{memory}\n\n"
    "Current screen elements:\n{elements}\n\n"
    "Known entities so far (persist across the whole run):\n{entities}\n\n"
    "Write a short analysis (3-4 sentences) as natural spoken commentary -- "
    "like a friend sitting on the couch, not a narrator reading the "
    "screen. Rules for the analysis:\n"
    "- Talk about what's actually happening and what it means for us -- "
    "the situation, the stakes, the story -- not a rundown of every stat "
    "and button visible on screen. Only bring up a specific number or "
    "element if it actually matters to the decision in front of us.\n"
    "- Refer to people and things by their natural name, the way someone "
    "would say it out loud ('Dolan', 'the fuel gauge'). Never repeat a UI "
    "label verbatim and never wrap words in square brackets in the "
    "analysis -- brackets are reserved for the actions list below only.\n"
    "- If there's dialogue, an event, or narrative text on screen, react "
    "to what it actually says, not just to the buttons that respond to it.\n"
    "- Don't just present the options neutrally. You have an opinion -- "
    "say what you'd actually do and why, the way a co-op partner would, "
    "not a screen reader listing choices.\n\n"
    "Then list a few specific candidate actions, e.g. 'Click the "
    "[flower pot]', wrapping the target noun in square brackets and "
    "referencing only the screen element ids given above in "
    "target_entity_ids -- this bracket notation belongs ONLY in the "
    "actions list, never in the analysis. List your recommended action "
    "first."
)

class Ally:
    def __init__(self, provider: GeminiProvider, base_personality: str = PERSONALITIES["Scout"]):
        self.provider = provider
        self.base_personality = base_personality

    def decide(
        self,
        elements_context: str,
        entities_context: str,
        genre_context: str = "unknown (not yet determined)",
        memory_context: str = "(no memory yet -- this is the first turn)",
        personality: str | None = None,
    ) -> AllyOutput:
        prompt = ALLY_PROMPT_TEMPLATE.format(
            personality=personality if personality else self.base_personality,
            genre=genre_context,
            memory=memory_context,
            elements=elements_context,
            entities=entities_context,
        )
        return self.provider.generate_structured(
            model=ALLY_MODEL,
            contents=[prompt],
            schema=AllyOutput,
            thinking_level="HIGH"
        )