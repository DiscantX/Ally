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

SCRIBE_MODEL = "gemini-3.5-flash-lite"

class Scribe:
    def __init__(self, provider: GeminiProvider):
        self.provider = provider

    def extract(self, image: Image.Image, include_ui: bool = True) -> ScribeOutput:
        prompt = SCRIBE_PROMPT_UI if include_ui else SCRIBE_PROMPT_NO_UI
        return self.provider.generate_structured(
            model=SCRIBE_MODEL,
            contents=[image, prompt],
            schema=ScribeOutput,
            thinking_level="minimal"
        )
