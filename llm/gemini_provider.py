"""Thin wrapper around google-genai.

This is the seam the earlier architecture discussion called for: both the
Scribe and Ally call generate_structured() rather than touching the genai
client directly. Swapping providers later (different Gemini model, a
different vendor entirely) means editing this one file.
"""

from google import genai
from google.genai import types, errors
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import TypeVar
import time
import random
import functools

load_dotenv()

T = TypeVar("T", bound=BaseModel)


def retry_with_gemini_backoff(max_retries: int = 5):
    """Decorator for handling Gemini rate limits (429) using retryDelay or exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(self, *args, **kwargs)
                except (errors.ClientError, errors.ServerError) as e:
                    attempt += 1
                    if attempt > max_retries:
                        raise
                    
                    delay = self._extract_retry_delay(e)
                    if delay is None:
                        delay = (2 ** attempt) + random.uniform(0, 1)
                    
                    time.sleep(delay)
        return wrapper
    return decorator


class GeminiProvider:
    def __init__(self, client: genai.Client | None = None):
        self.client = client or genai.Client()

    def _extract_retry_delay(self, error: Exception) -> float | None:
        try:
            details = getattr(error, "details", None)
            if isinstance(details, dict):
                err_obj = details.get("error", {})
                for detail_item in err_obj.get("details", []):
                    if isinstance(detail_item, dict) and "retryDelay" in detail_item:
                        delay_str = detail_item["retryDelay"]
                        if isinstance(delay_str, str) and delay_str.endswith("s"):
                            return float(delay_str[:-1])
        except Exception:
            pass
        return None

    @retry_with_gemini_backoff(max_retries=5)
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
