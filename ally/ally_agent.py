"""Agent B: Ally.

This is the "Blind Brain." Ally never receives the screenshot -- only the
State Sandbox's text summary and the Entity Registry's context. That's the
whole point of the air-gap: even if the underlying model has memorized a
walkthrough of this game, Ally is only ever handed facts your own pipeline
extracted this run, so it has nothing else to reason from.

Personality/player-relationship memory is wired via MemorySystem
(memory/manager.py) and PersonalityMemoryManager (memory/personality.py).
"""

from llm.gemini_provider import GeminiProvider
from schema.schema import AllyOutput, AllyChatOutput
from ally.personalities import PERSONALITIES
from prompts.ally import ALLY_PROMPT_TEMPLATE, ALLY_CHAT_PROMPT_TEMPLATE
from configs.config_manager import load_user_config

class Ally:
    def __init__(self, provider: GeminiProvider, base_personality: str = PERSONALITIES["Scout"], model: str | None = None, thinking_level: str | None = None):
        config = load_user_config()
        self.provider = provider
        self.base_personality = base_personality
        self.model = model or config["ally_model"]
        self.thinking_level = thinking_level or config["thinking_level"]

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
            model=self.model,
            contents=[prompt],
            schema=AllyOutput,
            thinking_level=self.thinking_level
        )

    def chat(
        self,
        elements_context: str,
        entities_context: str,
        genre_context: str = "unknown (not yet determined)",
        memory_context: str = "(no memory yet -- this is the first turn)",
        personality: str | None = None,
        question: str = "",
    ) -> AllyChatOutput:
        prompt = ALLY_CHAT_PROMPT_TEMPLATE.format(
            personality=personality if personality else self.base_personality,
            genre=genre_context,
            memory=memory_context,
            elements=elements_context,
            entities=entities_context,
            question=question,
        )
        return self.provider.generate_structured(
            model=self.model,
            contents=[prompt],
            schema=AllyChatOutput,
        )
