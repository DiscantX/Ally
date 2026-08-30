"""Gemini LLM Provider implementation using the Google GenAI Interactions API.

Inherits LLMProvider and RetryableProviderMixin.
Consolidates all streaming and non-streaming calls and fixes the thinking-stream
parsing bug (reading delta.content.text for thought_summary deltas).
"""

from google import genai
from google.genai import errors, types
from pydantic import BaseModel
from typing import TypeVar, Callable, Any, Iterator, Literal
from dataclasses import dataclass
import time
import random

from infrastructure.llm.base_provider import (
    LLMProvider,
    RetryableProviderMixin,
    _normalize_contents,
    TextContent,
    ImageContent,
)
from infrastructure.llm.model_lister import get_available_models as lister_get_available_models
from infrastructure.logger import log, timed
import partial_json_parser

T = TypeVar("T", bound=BaseModel)


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



@dataclass
class ParsedStreamEvent:
    kind: Literal["thought_chunk", "text_chunk"]
    text: str


def _iter_gemini_stream_events(raw_stream) -> Iterator[ParsedStreamEvent]:
    """The ONE place that reads event.delta.type, event.delta.content.text, event.delta.text.

    Verified against google-genai SDK Interactions API:
    - Thought summary deltas have delta.type == "thought_summary" and delta.content as a nested object with .text.
    - Text deltas have delta.type == "text" (or None) and delta.text directly or via delta.content.text / content string.
    """
    for event in raw_stream:
        delta = getattr(event, "delta", None)
        if not delta:
            chunk_text = getattr(event, "output_text", None) or getattr(event, "text", None)
            if chunk_text:
                yield ParsedStreamEvent(kind="text_chunk", text=chunk_text)
            continue

        delta_type = getattr(delta, "type", None)
        if not isinstance(delta_type, str):
            delta_type = None

        content = getattr(delta, "content", None)
        text_attr = getattr(delta, "text", None)

        if delta_type == "thought_summary":
            thought_text = ""
            if content is not None:
                if hasattr(content, "text") and isinstance(content.text, str):
                    thought_text = content.text
                elif isinstance(content, str):
                    thought_text = content
            if not thought_text and isinstance(text_attr, str):
                thought_text = text_attr
            if thought_text:
                yield ParsedStreamEvent(kind="thought_chunk", text=thought_text)
        elif delta_type == "text" or delta_type is None:
            chunk_text = ""
            if isinstance(text_attr, str):
                chunk_text = text_attr
            elif content is not None:
                if hasattr(content, "text") and isinstance(content.text, str):
                    chunk_text = content.text
                elif isinstance(content, str):
                    chunk_text = content
            if chunk_text:
                yield ParsedStreamEvent(kind="text_chunk", text=chunk_text)


class GeminiProvider(LLMProvider, RetryableProviderMixin):
    _first_gen_done = False

    def __init__(self, client: genai.Client | None = None):
        self.client = client or genai.Client()

    def _is_retryable_error(self, error: Exception) -> bool:
        return isinstance(error, (errors.ClientError, errors.ServerError, ValueError))

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

    def _to_provider_input(self, contents: Any) -> list[Any]:
        normalized = _normalize_contents(contents)
        formatted = []
        for item in normalized:
            if isinstance(item, TextContent):
                from google.genai._gaos.types.interactions.textcontent import TextContent as GenaiTextContent
                formatted.append(GenaiTextContent(type="text", text=item.text))
            elif isinstance(item, ImageContent):
                import base64
                from typing import cast
                from google.genai._gaos.types.interactions.imagecontent import ImageContent as GenaiImageContent
                b64_data = base64.b64encode(item.data).decode("utf-8")
                formatted.append(GenaiImageContent(type="image", data=b64_data, mime_type=cast(Any, item.mime_type)))
        return formatted

    def generate_structured(
        self,
        model: str,
        contents: Any,
        schema: type[T],
        thinking_level: str | types.ThinkingLevel | None = None,
        thinking_budget: int | None = None,
    ) -> T:
        def _call() -> T:
            start_t = time.perf_counter()
            generation_config: dict[str, Any] = {"thinking_summaries": "auto"}
            if thinking_level is not None:
                lvl = self._map_thinking_level(thinking_level)
                generation_config["thinking_level"] = lvl

            response = self.client.interactions.create(
                model=model,
                input=self._to_provider_input(contents),
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

        return self._retry_with_backoff(_call, max_retries=5)

    def generate_structured_stream(
        self,
        model: str,
        contents: Any,
        schema: type[T],
        thinking_level: str | types.ThinkingLevel | None = None,
        thinking_budget: int | None = None,
        on_thought_chunk: Callable[[str], None] | None = None,
    ) -> T:
        def _call() -> T:
            generation_config: dict[str, Any] = {"thinking_summaries": "auto"}
            if thinking_level is not None:
                lvl = self._map_thinking_level(thinking_level)
                generation_config["thinking_level"] = lvl

            stream = self.client.interactions.create(
                model=model,
                input=self._to_provider_input(contents),
                stream=True,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema.model_json_schema(),
                },
                generation_config=generation_config,
            )

            json_buffer = ""
            for event in _iter_gemini_stream_events(stream):
                if event.kind == "thought_chunk":
                    if on_thought_chunk is not None:
                        on_thought_chunk(event.text)
                elif event.kind == "text_chunk":
                    json_buffer += event.text

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

        return self._retry_with_backoff(_call, max_retries=5)

    def generate_structured_stream_field(
        self,
        model: str,
        contents: Any,
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
        attempt = 0
        while True:
            attempt += 1
            json_buffer = ""
            emitted_so_far = ""
            thought_begun = False
            try:
                generation_config: dict[str, Any] = {"thinking_summaries": "auto"}
                if thinking_level is not None:
                    lvl = self._map_thinking_level(thinking_level)
                    generation_config["thinking_level"] = lvl

                stream = self.client.interactions.create(
                    model=model,
                    input=self._to_provider_input(contents),
                    stream=True,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": schema.model_json_schema(),
                    },
                    generation_config=generation_config,
                )

                for event in _iter_gemini_stream_events(stream):
                    if event.kind == "thought_chunk":
                        if not thought_begun:
                            thought_begun = True
                            if on_thought_begin is not None:
                                on_thought_begin()
                        if on_thought_chunk is not None:
                            on_thought_chunk(event.text)
                    elif event.kind == "text_chunk":
                        if thought_begun:
                            thought_begun = False
                            if on_thought_finalize is not None:
                                on_thought_finalize()
                        json_buffer += event.text
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
                    log("Gemini streaming error (max retries {max_retries} exceeded): {e}", max_retries=max_retries, e=e)
                    raise

                if on_stream_reset is not None:
                    on_stream_reset()
                if on_thought_reset is not None:
                    on_thought_reset()

                delay = self._extract_retry_delay(e)
                if delay is None:
                    delay = (2 ** attempt) + random.uniform(0, 1)

                log("Gemini streaming error ({e}). Retrying attempt {attempt}/{max_retries} in {delay:.2f}s...", e=e, attempt=attempt, max_retries=max_retries, delay=delay)
                time.sleep(delay)

    def _extract_new_field_text(
        self, json_buffer: str, field_name: str, previous_value: str
    ) -> tuple[str, str]:
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

    def list_available_models(self) -> list[str]:
        return lister_get_available_models()

    def list_thinking_levels(self) -> list[str]:
        return get_available_thinking_levels()

    def supports_thinking(self, model: str) -> bool:
        m = model.lower()
        return "gemini-3" in m or "gemini-2.5" in m or "flash" in m or "pro" in m
