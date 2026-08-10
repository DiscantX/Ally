"""Thin wrapper around google-genai.

This is the seam the earlier architecture discussion called for: both the
Scribe and Ally call generate_structured() rather than touching the genai
client directly. Swapping providers later (different Gemini model, a
different vendor entirely) means editing this one file.
"""

from google import genai
from google.genai import types
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import TypeVar

load_dotenv()

T = TypeVar("T", bound=BaseModel)


class GeminiProvider:
    def __init__(self, client: genai.Client | None = None):
        self.client = client or genai.Client()

    def generate_structured(
        self,
        model: str,
        contents: list,
        schema: type[T],
    ) -> T:
        """Call the model and parse the response straight into `schema`.

        Using response_mime_type + response_schema instead of asking nicely
        for JSON in the prompt avoids the markdown-fence/stray-text problem
        the original script was exposed to.
        """
        response = self.client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        if not response.text:
            raise ValueError("Model returned empty response text")
        return schema.model_validate_json(response.text)
