"""Agent A: the Scribe.

Its only job is to look at the screenshot and report what's there. It never
suggests what to do, never speculates about the plot, and never gets asked
about the game's identity. Ally never sees this prompt or this image --
only what comes out the other end.
"""

import time
from PIL import Image

from infrastructure.llm.providers.gemini_provider import GeminiProvider
from brain.knowledge.schema.schema import ScribeOutput
from brain.knowledge.prompts.scribe import SCRIBE_PROMPT_UI, SCRIBE_PROMPT_NO_UI
from storage.configs.config_manager import load_user_config, get_model, get_thinking_level
from infrastructure.logger import log, timed

class Scribe:
    _first_extract_done = False

    def __init__(self, provider: GeminiProvider, model: str | None = None, thinking_level: str | None = None):
        config = load_user_config()
        self.provider = provider
        self.model = model or get_model("scribe_model", config)
        self.thinking_level = thinking_level or get_thinking_level("scribe", config)

    @timed
    def extract(self, image: Image.Image, include_ui: bool = True) -> ScribeOutput:
        start_t = time.perf_counter()
        prompt = SCRIBE_PROMPT_UI if include_ui else SCRIBE_PROMPT_NO_UI
        res = self.provider.generate_structured(
            model=self.model,
            contents=[image, prompt],
            schema=ScribeOutput,
            thinking_level=self.thinking_level
        )
        duration = time.perf_counter() - start_t
        log("Completed Scribe extraction in {duration:.4f}s (model={model})", duration=duration, model=self.model)
        return res
