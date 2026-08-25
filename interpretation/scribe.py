"""Agent A: the Scribe.

Its only job is to look at the screenshot and report what's there. It never
suggests what to do, never speculates about the plot, and never gets asked
about the game's identity. Ally never sees this prompt or this image --
only what comes out the other end.
"""

from PIL import Image

from llm.gemini_provider import GeminiProvider
from schema.schema import ScribeOutput
from prompts.scribe import SCRIBE_PROMPT_UI, SCRIBE_PROMPT_NO_UI
from configs.config_manager import load_user_config

class Scribe:
    def __init__(self, provider: GeminiProvider, model: str | None = None):
        config = load_user_config()
        self.provider = provider
        self.model = model or config["scribe_model"]
        self.thinking_level = config["thinking_level"]

    def extract(self, image: Image.Image, include_ui: bool = True) -> ScribeOutput:
        prompt = SCRIBE_PROMPT_UI if include_ui else SCRIBE_PROMPT_NO_UI
        return self.provider.generate_structured(
            model=self.model,
            contents=[image, prompt],
            schema=ScribeOutput,
            thinking_level=self.thinking_level
        )
