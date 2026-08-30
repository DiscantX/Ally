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

    @retry_with_gemini_backoff(max_retries=5)
    @timed
    def generate_soft_structured_stream_field(
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
        """Streams one named string field out of a soft-schema structured-output response using client.interactions.create(..., stream=True)."""
        generation_config: dict[str, Any] = {"thinking_summaries": "auto"}
        if thinking_level is not None:
            lvl = self._map_thinking_level(thinking_level)
            generation_config["thinking_level"] = lvl

        schema_instruction = f"You must respond ONLY with a single JSON object that strictly adheres to this schema: {schema.model_json_schema()}"

        attempt = 0
        while True:
            attempt += 1
            json_buffer = ""
            emitted_so_far = ""
            thought_begun = False
            try:
                response_stream = self.client.interactions.create(
                    model=model,
                    input=self._build_interactions_input(contents),
                    stream=True,
                    generation_config=generation_config,
                    system_instruction=schema_instruction,
                )
                for event in response_stream:
                    if hasattr(event, "step") and event.step:
                        step = event.step
                        if getattr(step, "type", None) == "thought" or "thought" in str(getattr(step, "type", "")).lower():
                            if not thought_begun:
                                thought_begun = True
                                if on_thought_begin is not None:
                                    on_thought_begin()
                            step_text = getattr(step, "text", None) or getattr(step, "content", None)
                            if isinstance(step_text, str) and step_text and on_thought_chunk is not None:
                                on_thought_chunk(step_text)
                            continue

                    delta = getattr(event, "delta", None)
                    if delta:
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
                        elif delta_type == "text" or delta_type is None:
                            if delta_text:
                                json_buffer += delta_text

                    chunk_text = getattr(event, "output_text", None)
                    if not chunk_text and hasattr(event, "text"):
                        chunk_text = event.text
                    if chunk_text and not delta:
                        json_buffer += chunk_text

                    if on_field_chunk is not None and json_buffer:
                        try:
                            cleaned_partial = json_buffer.strip()
                            if cleaned_partial.startswith("```"):
                                cleaned_partial = cleaned_partial.split("\n", 1)[-1]
                            partial_obj = partial_json_parser.loads(cleaned_partial, partial_json_parser.Allow.ALL)
                            if isinstance(partial_obj, dict) and stream_field in partial_obj:
                                val = partial_obj[stream_field]
                                if isinstance(val, str) and val.startswith(emitted_so_far):
                                    delta_val = val[len(emitted_so_far):]
                                    if delta_val:
                                        emitted_so_far = val
                                        on_field_chunk(delta_val)
                        except Exception:
                            pass

                if thought_begun and on_thought_finalize is not None:
                    on_thought_finalize()

                if not json_buffer:
                    log("Soft schema stream yielded empty buffer. Raw response object: {resp}", resp=str(response_stream))
                    raise ValueError("Soft schema streaming response produced no JSON content")

                try:
                    cleaned_json = json_buffer.strip()
                    if cleaned_json.startswith("```"):
                        cleaned_json = cleaned_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                        if cleaned_json.startswith("json"):
                            cleaned_json = cleaned_json[4:].strip()
                    parsed = schema.model_validate_json(cleaned_json)
                    final_val = getattr(parsed, stream_field, "")
                    if isinstance(final_val, str) and final_val.startswith(emitted_so_far):
                        remainder = final_val[len(emitted_so_far):]
                        if remainder and on_field_chunk is not None:
                            on_field_chunk(remainder)
                    return parsed
                except Exception as json_err:
                    try:
                        cleaned_json = json_buffer.strip()
                        if cleaned_json.startswith("```"):
                            cleaned_json = cleaned_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                            if cleaned_json.startswith("json"):
                                cleaned_json = cleaned_json[4:].strip()
                        partial_obj = partial_json_parser.loads(cleaned_json, partial_json_parser.Allow.ALL)
                        if isinstance(partial_obj, dict):
                            parsed = schema.model_validate(partial_obj)
                            final_val = getattr(parsed, stream_field, "")
                            if isinstance(final_val, str) and final_val.startswith(emitted_so_far):
                                remainder = final_val[len(emitted_so_far):]
                                if remainder and on_field_chunk is not None:
                                    on_field_chunk(remainder)
                            return parsed
                        raise json_err
                    except Exception as parse_err:
                        log("Failed to parse soft schema Interactions API output into schema. Raw text: {text}. Error: {e}", text=json_buffer, e=parse_err)
                        raise ValueError(f"Invalid JSON: {json_err}") from json_err

            except (errors.ClientError, errors.ServerError, Exception) as e:
                if attempt > max_retries:
                    log("Soft schema streaming error (max retries {max_retries} exceeded): {e}", max_retries=max_retries, e=e)
                    raise
                delay = self._extract_retry_delay(e)
                if delay is None:
                    delay = (2 ** attempt) + random.uniform(0, 1)
                log("Soft schema streaming error ({e}). Retrying attempt {attempt}/{max_retries} in {delay:.2f}s...", e=e, attempt=attempt, max_retries=max_retries, delay=delay)
                if on_stream_reset is not None:
                    on_stream_reset()
                if thought_begun and on_thought_reset is not None:
                    on_thought_reset()
                time.sleep(delay)

    @timed
    def generate_soft_structured_stream(
        self,
        model: str,
        contents: list,
        schema: type[T],
        thinking_level: str | types.ThinkingLevel | None = None,
        thinking_budget: int | None = None,
        thought_callback: Callable[[str], None] | None = None,
    ) -> T:
        """Alternative structured streaming method using client.interactions.create(..., stream=True)
        with soft schema instructions instead of strict response_format JSON schema constraints.

        Detailed Explanation:
        Strict JSON schema constraints in response_format can suppress or interfere with Gemini's
        internal thinking traces (thought summaries). By using soft schema instructions via system_instruction
        and client.interactions.create(..., stream=True), we allow the model to freely generate internal thought steps
        while guiding it to output a valid JSON object matching the requested Pydantic schema.
        """
        start_t = time.perf_counter()
        
        generation_config: dict[str, Any] = {"thinking_summaries": "auto"}
        if thinking_level is not None:
            generation_config["thinking_level"] = self._map_thinking_level(thinking_level)

        schema_instruction = f"You must respond ONLY with a single JSON object that strictly adheres to this schema: {schema.model_json_schema()}"

        response_stream = self.client.interactions.create(
            model=model,
            input=self._build_interactions_input(contents),
            stream=True,
            generation_config=generation_config,
            system_instruction=schema_instruction,
        )

        full_text_response = ""

        for event in response_stream:
            if hasattr(event, "step") and event.step:
                step = event.step
                if getattr(step, "type", None) == "thought" or "thought" in str(getattr(step, "type", "")).lower():
                    step_text = getattr(step, "text", None) or getattr(step, "content", None)
                    if isinstance(step_text, str) and step_text and thought_callback:
                        thought_callback(step_text)
                    continue

            delta = getattr(event, "delta", None)
            if delta:
                delta_type = getattr(delta, "type", None)
                if not isinstance(delta_type, str):
                    delta_type = None
                delta_content = getattr(delta, "content", None)
                delta_text_attr = getattr(delta, "text", None)
                delta_text = delta_content if isinstance(delta_content, str) else (delta_text_attr if isinstance(delta_text_attr, str) else "")
                
                if delta_type == "thought_summary":
                    if thought_callback and delta_text:
                        thought_callback(delta_text)
                elif delta_type == "text" or delta_type is None:
                    if delta_text:
                        full_text_response += delta_text

            chunk_text = getattr(event, "output_text", None)
            if not chunk_text and hasattr(event, "text"):
                chunk_text = event.text
            if chunk_text and not delta:
                full_text_response += chunk_text

        duration = time.perf_counter() - start_t
        if not GeminiProvider._first_gen_done:
            GeminiProvider._first_gen_done = True
            log("Completed first soft-schema LLM generation (model={model}) in {duration:.4f}s", model=model, duration=duration)

        if not full_text_response:
            log("Soft schema stream yielded empty full_text_response. Raw response object: {resp}", resp=str(response_stream))
            raise ValueError("Soft schema streaming response produced no JSON content")

        try:
            cleaned_json = full_text_response.strip()
            if cleaned_json.startswith("```"):
                cleaned_json = cleaned_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                if cleaned_json.startswith("json"):
                    cleaned_json = cleaned_json[4:].strip()
            return schema.model_validate_json(cleaned_json)
        except Exception as e:
            try:
                cleaned_json = full_text_response.strip()
                if cleaned_json.startswith("```"):
                    cleaned_json = cleaned_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    if cleaned_json.startswith("json"):
                        cleaned_json = cleaned_json[4:].strip()
                partial_obj = partial_json_parser.loads(cleaned_json, partial_json_parser.Allow.ALL)
                if isinstance(partial_obj, dict):
                    return schema.model_validate(partial_obj)
                raise e
            except Exception as parse_err:
                log("Failed to parse soft schema Interactions API output into schema. Raw text: {text}. Error: {e}", text=full_text_response, e=parse_err)
                raise parse_err

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
