"""Agent B: Ally.

This is the "Blind Brain." Ally never receives the screenshot -- only the
State Sandbox's text summary and the Entity Registry's context. That's the
whole point of the air-gap: even if the underlying model has memorized a
walkthrough of this game, Ally is only ever handed facts your own pipeline
extracted this run, so it has nothing else to reason from.

Personality/player-relationship memory is wired via MemorySystem
(memory/manager.py) and PersonalityMemoryManager (memory/personality.py).
"""

from typing import Callable
from infrastructure.llm.providers.gemini_provider import GeminiProvider
from brain.knowledge.schema.schema import AllyOutput, AllyChatOutput
from brain.reasoning.personalities import PERSONALITIES
from brain.knowledge.prompts.ally import ALLY_PROMPT_TEMPLATE, ALLY_CHAT_PROMPT_TEMPLATE
from cabinet.configs.config_manager import load_user_config, get_model, get_thinking_level

class Ally:
    def __init__(self, provider: GeminiProvider, base_personality: str | None = None, model: str | None = None, thinking_level: str | None = None) -> None:
        if provider is None:
            raise ValueError("provider must not be None")
        config = load_user_config()
        self.provider = provider
        if base_personality is None:
            default_p = config.get("default_personality", "Scout")
            self.base_personality = PERSONALITIES.get(default_p, PERSONALITIES["Scout"])
        else:
            self.base_personality = PERSONALITIES.get(base_personality, base_personality)
        self.model = model or get_model("ally_model", config)
        self.thinking_level = thinking_level or get_thinking_level("ally", config)

    def decide(
        self,
        elements_context: str,
        entities_context: str,
        genre_context: str = "unknown (not yet determined)",
        memory_context: str = "(no memory yet -- this is the first turn)",
        personality: str | None = None,
        perspective_context: str = "(no strong perspective signal this turn)",
    ) -> AllyOutput:
        prompt = ALLY_PROMPT_TEMPLATE.format(
            personality=personality if personality else self.base_personality,
            genre=genre_context,
            memory=memory_context,
            elements=elements_context,
            entities=entities_context,
            perspectives=perspective_context,
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

    def decide_stream(
        self,
        elements_context: str,
        entities_context: str,
        genre_context: str = "unknown (not yet determined)",
        memory_context: str = "(no memory yet -- this is the first turn)",
        personality: str | None = None,
        perspective_context: str = "(no strong perspective signal this turn)",
        on_chunk: Callable[[str], None] | None = None,
        on_reset: Callable[[], None] | None = None,
        on_thought_begin: Callable[[], None] | None = None,
        on_thought_chunk: Callable[[str], None] | None = None,
        on_thought_reset: Callable[[], None] | None = None,
        on_thought_finalize: Callable[[], None] | None = None,
    ) -> AllyOutput:
        """Streaming counterpart to decide() -- builds the exact same prompt,
        but streams the `analysis` field live via on_chunk as it's generated,
        with on_reset called if a mid-stream retry occurs."""
        prompt = ALLY_PROMPT_TEMPLATE.format(
            personality=personality if personality else self.base_personality,
            genre=genre_context,
            memory=memory_context,
            elements=elements_context,
            entities=entities_context,
            perspectives=perspective_context,
        )
        return self.provider.generate_structured_stream_field(
            model=self.model,
            contents=[prompt],
            schema=AllyOutput,
            stream_field="analysis",
            on_field_chunk=on_chunk,
            on_stream_reset=on_reset,
            thinking_level=self.thinking_level,
            on_thought_begin=on_thought_begin,
            on_thought_chunk=on_thought_chunk,
            on_thought_reset=on_thought_reset,
            on_thought_finalize=on_thought_finalize,
        )

    def chat_stream(
        self,
        elements_context: str,
        entities_context: str,
        genre_context: str = "unknown (not yet determined)",
        memory_context: str = "(no memory yet -- this is the first turn)",
        personality: str | None = None,
        question: str = "",
        on_chunk: Callable[[str], None] | None = None,
        on_reset: Callable[[], None] | None = None,
        on_thought_begin: Callable[[], None] | None = None,
        on_thought_chunk: Callable[[str], None] | None = None,
        on_thought_reset: Callable[[], None] | None = None,
        on_thought_finalize: Callable[[], None] | None = None,
    ) -> AllyChatOutput:
        """Streaming counterpart to chat() -- builds the exact same prompt,
        streams the `response` field live via on_chunk."""
        prompt = ALLY_CHAT_PROMPT_TEMPLATE.format(
            personality=personality if personality else self.base_personality,
            genre=genre_context,
            memory=memory_context,
            elements=elements_context,
            entities=entities_context,
            question=question,
        )
        return self.provider.generate_structured_stream_field(
            model=self.model,
            contents=[prompt],
            schema=AllyChatOutput,
            stream_field="response",
            on_field_chunk=on_chunk,
            on_stream_reset=on_reset,
            thinking_level=self.thinking_level,
            on_thought_begin=on_thought_begin,
            on_thought_chunk=on_thought_chunk,
            on_thought_reset=on_thought_reset,
            on_thought_finalize=on_thought_finalize,
        )
