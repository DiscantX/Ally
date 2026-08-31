"""Gemini LLM Provider implementation using the Google GenAI Interactions API.

Inherits LLMProvider and RetryableProviderMixin.
Consolidates all streaming and non-streaming calls and fixes the thinking-stream
parsing bug (reading delta.content.text for thought_summary deltas).
"""

from google import genai
from google.genai import errors, types
from google.genai._gaos.types.interactions.textcontent import TextContent as GenaiTextContent
from google.genai._gaos.types.interactions.imagecontent import ImageContent as GenaiImageContent
from pydantic import BaseModel
from typing import TypeVar, Callable, Any, Iterator, Literal
from dataclasses import dataclass
import json
import time
import random
from dotenv import load_dotenv

load_dotenv(override=True)

from infrastructure.llm.base_provider import (
    LLMProvider,
    RetryableProviderMixin,
    _normalize_contents,
    TextContent,
    ImageContent,
)
from infrastructure.logger import log, timed
import partial_json_parser

T = TypeVar("T", bound=BaseModel)


@timed
def get_available_models() -> list[str]:
    """Fetch models dynamically from Gemini SDK, fallback to static file on error."""
    try:
        client = genai.Client()
        models_list = list(client.models.list())
        models = [
            m.name.replace("models/", "") for m in models_list
            if m.name and "gemini" in m.name and "embedding" not in m.name and "veo" not in m.name and "aqa" not in m.name
        ]
        return sorted(models)
    except Exception as e:
        log("Failed to fetch models dynamically: {e}. Falling back to static config.", e=e)
        try:
            with open("configs/supported_models.json", "r") as f:
                return json.load(f)["supported_models"]
        except Exception as e_static:
            log("Failed to load fallback static config: {e_static}", e_static=e_static)
            return ["gemini-3.5-flash-lite"]


def get_available_thinking_levels() -> list[str]:
    """Dynamically extract valid thinking levels from google.genai.types.ThinkingLevel."""
    try:
        if hasattr(types, "ThinkingLevel"):
            levels = [
                (item.name if hasattr(item, "name") else str(item)).lower()
                for item in types.ThinkingLevel
                if (item.name if hasattr(item, "name") else str(item)).upper() != "THINKING_LEVEL_UNSPECIFIED"
            ]
            if levels:
                return levels
    except Exception:
        pass
    return ["minimal", "low", "medium", "high"]


@dataclass
class ParsedStreamEvent:
    kind: Literal["thought_chunk", "text_chunk"]
    text: str


def _extract_delta_text(content: Any, text_attr: Any) -> str:
    """Extract text from delta content or text attribute."""
    if content is not None:
        if hasattr(content, "text") and isinstance(content.text, str):
            return content.text
        if isinstance(content, str):
            return content
    if isinstance(text_attr, str):
        return text_attr
    return ""


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

        text = _extract_delta_text(content, text_attr)
        if text:
            if delta_type == "thought_summary":
                yield ParsedStreamEvent(kind="thought_chunk", text=text)
            elif delta_type == "text" or delta_type is None:
                yield ParsedStreamEvent(kind="text_chunk", text=text)


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
            name = getattr(thinking_level, "name", "").lower()
            if not name or name == "thinking_level_unspecified":
                return None
            return name

        s = str(thinking_level).strip().lower()
        for prefix in ["thinking_level_", "thinking_"]:
            if s.startswith(prefix):
                s = s[len(prefix):]

        if not s or s == "unspecified":
            return None

        try:
            if hasattr(types, "ThinkingLevel"):
                for item in types.ThinkingLevel:
                    item_name = getattr(item, "name", "").lower()
                    pure_name = item_name
                    for prefix in ["thinking_level_", "thinking_"]:
                        if pure_name.startswith(prefix):
                            pure_name = pure_name[len(prefix):]
                    if item_name == s or pure_name == s or str(getattr(item, "value", "")).lower() == s:
                        if item_name == "thinking_level_unspecified":
                            return None
                        return item_name
        except Exception:
            pass

        return s

    def _to_provider_input(self, contents: Any) -> list[Any]:
        normalized = _normalize_contents(contents)
        formatted = []
        for item in normalized:
            if isinstance(item, TextContent):
                formatted.append(GenaiTextContent(type="text", text=item.text))
            elif isinstance(item, ImageContent):
                import base64
                from typing import cast
                b64_data = base64.b64encode(item.data).decode("utf-8")
                formatted.append(GenaiImageContent(type="image", data=b64_data, mime_type=cast(Any, item.mime_type)))
        return formatted

    def _create_interaction(
        self,
        model: str,
        contents: Any,
        schema: type[T],
        thinking_level: str | types.ThinkingLevel | None = None,
        thinking_budget: int | None = None,
        stream: bool = False,
    ) -> Any:
        generation_config: dict[str, Any] = {"thinking_summaries": "auto"}
        lvl = self._map_thinking_level(thinking_level)
        if lvl is not None:
            generation_config["thinking_level"] = lvl
        if thinking_budget is not None:
            generation_config["thinking_budget"] = thinking_budget

        kwargs: dict[str, Any] = {
            "model": model,
            "input": self._to_provider_input(contents),
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema.model_json_schema(),
            },
            "generation_config": generation_config,
        }
        if stream:
            kwargs["stream"] = True

        return self.client.interactions.create(**kwargs)

    def _parse_json_buffer(self, json_buffer: str, schema: type[T]) -> T:
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
            response = self._create_interaction(model, contents, schema, thinking_level, thinking_budget, stream=False)
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
            stream = self._create_interaction(model, contents, schema, thinking_level, thinking_budget, stream=True)
            json_buffer = ""
            for event in _iter_gemini_stream_events(stream):
                if event.kind == "thought_chunk":
                    if on_thought_chunk is not None:
                        on_thought_chunk(event.text)
                elif event.kind == "text_chunk":
                    json_buffer += event.text

            return self._parse_json_buffer(json_buffer, schema)

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
                stream = self._create_interaction(model, contents, schema, thinking_level, thinking_budget, stream=True)

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

                return self._parse_json_buffer(json_buffer, schema)

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
        return get_available_models()

    def list_thinking_levels(self) -> list[str]:
        return get_available_thinking_levels()

    def supports_thinking(self, model: str) -> bool:
        m = model.lower()
        return "gemini-3" in m or "gemini-2.5" in m or "flash" in m or "pro" in m
