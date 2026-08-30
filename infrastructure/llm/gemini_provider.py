"""Thin wrapper around google-genai using the Interactions API.

This is the seam: both Scribe and Ally call generate_structured() rather than
touching the genai client directly. Swapping providers later means editing this one file.
"""

from google import genai
from google.genai import errors, types
from google.genai._gaos.types.interactions.textcontent import TextContent
from google.genai._gaos.types.interactions.imagecontent import ImageContent
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import TypeVar, Callable, Any
import io
import base64
import time
import random
import functools
from PIL import Image
import partial_json_parser
from infrastructure.logger import log, timed

load_dotenv(override=True)

T = TypeVar("T", bound=BaseModel)


def retry_with_gemini_backoff(max_retries: int = 5):
    """Decorator for handling Gemini rate limits (429) using retryDelay or exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        @timed
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

    def _map_thinking_level(self, thinking_level: str | types.ThinkingLevel | None) -> str | None:
        if thinking_level is None:
            return None
        if isinstance(thinking_level, types.ThinkingLevel):
            if thinking_level == getattr(types.ThinkingLevel, "THINKING_LEVEL_UNSPECIFIED", None):
                return None
            return thinking_level.name.lower()
        if isinstance(thinking_level, str):
            s = thinking_level.lower()
            if s == "thinking_level_unspecified" or s == "":
                return None
            val_upper = thinking_level.upper()
            try:
                if hasattr(types.ThinkingLevel, val_upper):
                    item = getattr(types.ThinkingLevel, val_upper)
                    if item != getattr(types.ThinkingLevel, "THINKING_LEVEL_UNSPECIFIED", None):
                        if hasattr(item, "name"):
                            return item.name.lower()
            except Exception:
                pass
            try:
                for item in types.ThinkingLevel:
                    if item.name.upper() == val_upper or str(item.value).upper() == val_upper:
                        if item != getattr(types.ThinkingLevel, "THINKING_LEVEL_UNSPECIFIED", None):
                            if hasattr(item, "name"):
                                return item.name.lower()
            except Exception:
                pass
            for item in types.ThinkingLevel:
                if item.name.lower() == s:
                    if item != getattr(types.ThinkingLevel, "THINKING_LEVEL_UNSPECIFIED", None):
                        if hasattr(item, "name"):
                            return item.name.lower()
            if s in ["minimal", "low", "medium", "high"]:
                return s
            return s
        return str(thinking_level).lower()

    def _build_interactions_input(self, contents: Any) -> list[Any]:
        """Converts contents list into Interactions API input objects.

        Confirmed via Phase 0 verification (live calls in §1.2 run and succeeded):
        - TextContent: Fields `text` (required, str), `type` (optional literal 'text'), `annotations`
        - ImageContent: Fields `data` (optional str, base64-encoded string), `mime_type` (optional literal 'image/png'), `type` (optional literal 'image'), `uri`, `resolution`
        - input= Shape: Accepts a list of content objects (e.g. [TextContent, ImageContent]) directly, WITHOUT wrapping in a Turn object.
        """
        if contents is None:
            return []
        if not isinstance(contents, list):
            contents = [contents]

        formatted = []
        for item in contents:
            if isinstance(item, str):
                formatted.append(TextContent(type="text", text=item))
            elif isinstance(item, Image.Image):
                buffered = io.BytesIO()
                img_format = item.format or "PNG"
                item.save(buffered, format=img_format)
                img_bytes = buffered.getvalue()
                mime_type = f"image/{img_format.lower()}"
                if mime_type == "image/jpg":
                    mime_type = "image/jpeg"
                elif mime_type not in ["image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"]:
                    mime_type = "image/png"
                b64_data = base64.b64encode(img_bytes).decode("utf-8")
                formatted.append(ImageContent(type="image", data=b64_data, mime_type=mime_type))
            else:
                raise TypeError(f"Unsupported content type for Interactions API: {type(item).__name__}")
        return formatted

    @retry_with_gemini_backoff(max_retries=5)
    @timed
    def generate_structured(
        self,
        model: str,
        contents: list,
        schema: type[T],
        thinking_level: str | types.ThinkingLevel | None = None,
        thinking_budget: int | None = None,
    ) -> T:
        """Call the model via client.interactions.create and parse straight into `schema`."""
        start_t = time.perf_counter()
        generation_config: dict[str, Any] = {"thinking_summaries": "auto"}
        if thinking_level is not None:
            lvl = self._map_thinking_level(thinking_level)
            generation_config["thinking_level"] = lvl

        response = self.client.interactions.create(
            model=model,
            input=self._build_interactions_input(contents),
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema.model_json_schema(),
            },
            generation_config=generation_config,
        )

        duration = time.perf_counter() - start_t
        if not GeminiProvider._first_gen_done:
            GeminiProvider._first_gen_done = True
            log("Completed first LLM generation (model={model}) in {duration:.4f}s", model=model, duration=duration)

        text_content = getattr(response, "output_text", None) or getattr(response, "text", None)
        if not text_content:
            raise ValueError("Model returned empty response text")
        return schema.model_validate_json(text_content)

    @timed
    def generate_structured_stream(
        self,
        model: str,
        contents: list,
        schema: type[T],
        thinking_level: str | types.ThinkingLevel | None = None,
        thinking_budget: int | None = None,
        on_thought_chunk: Callable[[str], None] | None = None,
    ) -> T:
        """Streaming counterpart to generate_structured() using client.interactions.create(..., stream=True)."""
        generation_config: dict[str, Any] = {"thinking_summaries": "auto"}
        if thinking_level is not None:
            lvl = self._map_thinking_level(thinking_level)
            generation_config["thinking_level"] = lvl

        json_buffer = ""
        stream = self.client.interactions.create(
            model=model,
            input=self._build_interactions_input(contents),
            stream=True,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema.model_json_schema(),
            },
            generation_config=generation_config,
        )
        for event in stream:
            delta = getattr(event, "delta", None)
            if not delta:
                continue
            delta_type = getattr(delta, "type", None)
            if not isinstance(delta_type, str):
                delta_type = None
            delta_content = getattr(delta, "content", None)
            delta_text_attr = getattr(delta, "text", None)
            delta_text = delta_content if isinstance(delta_content, str) else (delta_text_attr if isinstance(delta_text_attr, str) else "")
            if delta_type == "thought_summary":
                if on_thought_chunk is not None and delta_text:
                    on_thought_chunk(delta_text)
            elif delta_type == "text" or delta_type is None:
                if delta_text:
                    json_buffer += delta_text

        if not json_buffer:
            raise ValueError("Streaming response produced no JSON content")
        try:
            return schema.model_validate_json(json_buffer)
        except Exception as json_err:
            try:
                partial_obj = partial_json_parser.loads(json_buffer, partial_json_parser.Allow.ALL)
                if isinstance(partial_obj, dict):
                    return schema.model_validate(partial_obj)
                raise json_err
            except Exception as parse_err:
                log("Failed to parse final JSON buffer via partial_json_parser: {e}", e=parse_err)
                raise ValueError(f"Invalid JSON: {json_err}") from json_err

    @timed
    def generate_structured_stream_field(
        self,
        model: str,
        contents: list,
        schema: type[T],
        stream_field: str,
        on_field_chunk: Callable[[str], None] | None = None,
        on_stream_reset: Callable[[], None] | None = None,
        thinking_level: str | types.ThinkingLevel | None = None,
        thinking_budget: int | None = None,
        max_retries: int = 5,
        on_thought_chunk: Callable[[str], None] | None = None,
        on_thought_begin: Callable[[], None] | None = None,
        on_thought_finalize: Callable[[], None] | None = None,
        on_thought_reset: Callable[[], None] | None = None,
    ) -> T:
        """Streams one named string field out of a structured-output response using client.interactions.create(..., stream=True)."""
        generation_config: dict[str, Any] = {"thinking_summaries": "auto"}
        if thinking_level is not None:
            lvl = self._map_thinking_level(thinking_level)
            generation_config["thinking_level"] = lvl

        attempt = 0
        while True:
            attempt += 1
            json_buffer = ""
            emitted_so_far = ""
            thought_begun = False
            try:
                stream = self.client.interactions.create(
                    model=model,
                    input=self._build_interactions_input(contents),
                    stream=True,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": schema.model_json_schema(),
                    },
                    generation_config=generation_config,
                )
                for event in stream:
                    delta = getattr(event, "delta", None)
                    if not delta:
                        continue
                    delta_type = getattr(delta, "type", None)
                    if not isinstance(delta_type, str):
                        delta_type = None
                    delta_content = getattr(delta, "content", None)
                    delta_text_attr = getattr(delta, "text", None)
                    delta_text = delta_content if isinstance(delta_content, str) else (delta_text_attr if isinstance(delta_text_attr, str) else "")

                    if delta_type == "thought_summary":
                        if not thought_begun:
                            thought_begun = True
                            if on_thought_begin is not None:
                                on_thought_begin()
                        if on_thought_chunk is not None and delta_text:
                            on_thought_chunk(delta_text)
                    else:
                        if thought_begun:
                            thought_begun = False
                            if on_thought_finalize is not None:
                                on_thought_finalize()
                        if delta_text:
                            json_buffer += delta_text
                            if on_field_chunk is not None:
                                new_text, emitted_so_far = self._extract_new_field_text(
                                    json_buffer, stream_field, emitted_so_far
                                )
                                if new_text:
                                    on_field_chunk(new_text)

                if thought_begun:
                    thought_begun = False
                    if on_thought_finalize is not None:
                        on_thought_finalize()

                if not json_buffer:
                    raise ValueError("Streaming response produced no JSON content")
                try:
                    return schema.model_validate_json(json_buffer)
                except Exception as json_err:
                    try:
                        partial_obj = partial_json_parser.loads(json_buffer, partial_json_parser.Allow.ALL)
                        if isinstance(partial_obj, dict):
                            return schema.model_validate(partial_obj)
                        raise json_err
                    except Exception as parse_err:
                        log("Failed to parse final JSON buffer via partial_json_parser: {e}", e=parse_err)
                        raise ValueError(f"Invalid JSON: {json_err}") from json_err

            except (errors.ClientError, errors.ServerError, ValueError) as e:
                if thought_begun:
                    thought_begun = False
                    if on_thought_finalize is not None:
                        on_thought_finalize()
                if attempt > max_retries:
                    log(
                        "Gemini streaming error (max retries {max_retries} exceeded): {e}",
                        max_retries=max_retries, e=e,
                    )
                    raise

                if on_stream_reset is not None:
                    on_stream_reset()
                if on_thought_reset is not None:
                    on_thought_reset()

                delay = None
                if isinstance(e, (errors.ClientError, errors.ServerError)):
                    delay = self._extract_retry_delay(e)
                if delay is None:
                    delay = (2 ** attempt) + random.uniform(0, 1)

                log(
                    "Gemini streaming error ({e}). Retrying attempt {attempt}/{max_retries} in {delay:.2f}s...",
                    e=e, attempt=attempt, max_retries=max_retries, delay=delay,
                )
                time.sleep(delay)

    def _extract_new_field_text(
        self, json_buffer: str, field_name: str, previous_value: str
    ) -> tuple[str, str]:
        """Best-effort incremental extraction of `field_name`'s growing
        string value from a possibly-incomplete JSON buffer. Returns
        (new_suffix_to_emit_now, updated_previous_value).

        # Verified against google-genai==2.19.0 and partial_json_parser==0.2.1.1.post7
        # installed in this environment. client.interactions.create(..., stream=True)
        # produces events with delta.type == "thought_summary" and delta.type == "text".
        """
        try:
            partial_obj = partial_json_parser.loads(json_buffer, partial_json_parser.Allow.ALL)
        except Exception:
            return "", previous_value

        if not isinstance(partial_obj, dict):
            return "", previous_value

        current_value = partial_obj.get(field_name)
        if not isinstance(current_value, str):
            return "", previous_value

        if current_value.startswith(previous_value) and len(current_value) > len(previous_value):
            return current_value[len(previous_value):], current_value

        return "", previous_value
