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
from typing import TypeVar, Callable
import time
import random
import functools
from infrastructure.logger import log

load_dotenv(override=True)

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
                        log("Gemini API error (max retries {max_retries} exceeded): {e}", max_retries=max_retries, e=e)
                        raise
                    
                    delay = self._extract_retry_delay(e)
                    if delay is None:
                        delay = (2 ** attempt) + random.uniform(0, 1)
                    
                    log("Gemini API error ({e}). Retrying attempt {attempt}/{max_retries} in {delay:.2f}s...", e=e, attempt=attempt, max_retries=max_retries, delay=delay)
                    time.sleep(delay)
        return wrapper
    return decorator


def get_available_thinking_levels() -> list[str]:
    """Dynamically extract valid thinking levels from google.genai.types.ThinkingLevel."""
    levels = []
    try:
        if hasattr(types, "ThinkingLevel"):
            for item in types.ThinkingLevel:
                if hasattr(item, "name"):
                    levels.append(item.name.lower())
                elif isinstance(item, str):
                    levels.append(item.lower())
    except Exception:
        pass
    if not levels:
        levels = ["minimal", "low", "medium", "high"]
    return levels


class GeminiProvider:
    _first_gen_done = False

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

    def _map_thinking_level(self, thinking_level: str | types.ThinkingLevel | None) -> Any:
        if thinking_level is None:
            return None
        if isinstance(thinking_level, types.ThinkingLevel):
            return thinking_level
        if isinstance(thinking_level, str):
            val_upper = thinking_level.upper()
            try:
                if hasattr(types.ThinkingLevel, val_upper):
                    return getattr(types.ThinkingLevel, val_upper)
            except Exception:
                pass
            try:
                for item in types.ThinkingLevel:
                    if item.name.upper() == val_upper or str(item.value).upper() == val_upper:
                        return item
            except Exception:
                pass
            for item in types.ThinkingLevel:
                if item.name.lower() == thinking_level.lower():
                    return item
        return thinking_level

    @retry_with_gemini_backoff(max_retries=5)
    def generate_structured(
        self,
        model: str,
        contents: list,
        schema: type[T],
        thinking_level: str | types.ThinkingLevel | None = None,
    ) -> T:
        """Call the model and parse the response straight into `schema`.

        Using response_mime_type + response_schema instead of asking nicely
        for JSON in the prompt avoids the markdown-fence/stray-text problem
        the original script was exposed to.
        """
        start_t = time.perf_counter()
        thinking_config = None
        if thinking_level is not None:
            lvl = self._map_thinking_level(thinking_level)
            thinking_config = types.ThinkingConfig(thinking_level=lvl)

        response = self.client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                thinking_config=thinking_config,
            ),
        )
        duration = time.perf_counter() - start_t
        if not GeminiProvider._first_gen_done:
            GeminiProvider._first_gen_done = True
            log("Completed first LLM generation (model={model}) in {duration:.4f}s", model=model, duration=duration)

        if not response.text:
            raise ValueError("Model returned empty response text")
        return schema.model_validate_json(response.text)

    def generate_structured_stream(
        self,
        model: str,
        contents: list,
        schema: type[T],
        thinking_level: str | types.ThinkingLevel | None = None,
        on_thought_chunk: Callable[[str], None] | None = None,
    ) -> T:
        """Streaming counterpart to generate_structured(). Requests
        include_thoughts=True alongside the same response_mime_type/
        response_schema structured-output config used everywhere else.

        Per Gemini's two-phase stream contract when include_thoughts and a
        strict response_schema are both set: the model emits ALL thought
        chunks first (plain text, part.thought=True), then ALL JSON content
        chunks second (part.text, part.thought falsy). Partial JSON is not
        valid JSON until the stream completes -- this method never hands a
        partial chunk to json.loads() or to the caller. If on_thought_chunk
        is given, it's called once per thought-chunk's text as it arrives
        (e.g. to print it live to the terminal); JSON content chunks are
        buffered internally and the full buffer is parsed into `schema`
        only once the stream ends, exactly like generate_structured()'s
        non-streaming parse step.
        """
        thinking_config = None
        if thinking_level is not None:
            lvl = self._map_thinking_level(thinking_level)
            thinking_config = types.ThinkingConfig(thinking_level=lvl, include_thoughts=True)

        json_buffer = ""
        stream = self.client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                thinking_config=thinking_config,
            ),
        )
        for chunk in stream:
            if not chunk.candidates:
                continue
            for part in chunk.candidates[0].content.parts:
                if getattr(part, "thought", False):
                    if part.text and on_thought_chunk is not None:
                        on_thought_chunk(part.text)
                elif part.text:
                    json_buffer += part.text

        if not json_buffer:
            raise ValueError("Streaming response produced no JSON content")
        return schema.model_validate_json(json_buffer)
