"""Provider-agnostic base interface, content types, and retry mixin for LLM integrations.

This module contains zero vendor SDK imports (no google.genai, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeVar, Callable, Any, Literal
import io
import base64
import time
import random
from PIL import Image
from pydantic import BaseModel
from infrastructure.logger import log

T = TypeVar("T", bound=BaseModel)


@dataclass
class TextContent:
    text: str


@dataclass
class ImageContent:
    """Raw image bytes + mime type. Callers pass PIL.Image.Image objects,
    which are normalized into this shape before dispatch to provider implementations.
    """
    data: bytes
    mime_type: str


Content = TextContent | ImageContent


def _normalize_contents(contents: Any) -> list[Content]:
    """Normalize input contents (strings, PIL Images, or lists thereof) into provider-agnostic Content objects."""
    if contents is None:
        return []
    if not isinstance(contents, list):
        contents = [contents]

    normalized: list[Content] = []
    for item in contents:
        if isinstance(item, str):
            normalized.append(TextContent(text=item))
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
            normalized.append(ImageContent(data=img_bytes, mime_type=mime_type))
        elif hasattr(item, "text") and isinstance(getattr(item, "text", None), str):
            normalized.append(TextContent(text=item.text))
        elif hasattr(item, "data") and hasattr(item, "mime_type"):
            normalized.append(ImageContent(data=item.data, mime_type=item.mime_type))
        else:
            raise TypeError(f"Unsupported content type: {type(item).__name__}")
    return normalized


class RetryableProviderMixin(ABC):
    """Generic retry-with-backoff scaffolding."""

    @abstractmethod
    def _is_retryable_error(self, error: Exception) -> bool:
        pass

    @abstractmethod
    def _extract_retry_delay(self, error: Exception) -> float | None:
        pass

    def _retry_with_backoff(self, func: Callable[[], T], max_retries: int = 5) -> T:
        attempt = 0
        while True:
            try:
                return func()
            except Exception as e:
                attempt += 1
                if attempt > max_retries or not self._is_retryable_error(e):
                    log("LLM provider error (max retries {max_retries} exceeded or non-retryable): {e}", max_retries=max_retries, e=e)
                    raise
                
                delay = self._extract_retry_delay(e)
                if delay is None:
                    delay = (2 ** attempt) + random.uniform(0, 1)
                
                log("LLM provider error ({e}). Retrying attempt {attempt}/{max_retries} in {delay:.2f}s...", e=e, attempt=attempt, max_retries=max_retries, delay=delay)
                time.sleep(delay)


class LLMProvider(ABC):
    """Abstract base class for all LLM providers (Gemini, OpenRouter, etc.)."""

    @abstractmethod
    def generate_structured(
        self,
        model: str,
        contents: Any,
        schema: type[T],
        thinking_level: str | None = None,
        thinking_budget: int | None = None,
    ) -> T:
        pass

    @abstractmethod
    def generate_structured_stream_field(
        self,
        model: str,
        contents: Any,
        schema: type[T],
        stream_field: str,
        on_field_chunk: Callable[[str], None] | None = None,
        on_stream_reset: Callable[[], None] | None = None,
        thinking_level: str | None = None,
        thinking_budget: int | None = None,
        max_retries: int = 5,
        on_thought_chunk: Callable[[str], None] | None = None,
        on_thought_begin: Callable[[], None] | None = None,
        on_thought_finalize: Callable[[], None] | None = None,
        on_thought_reset: Callable[[], None] | None = None,
    ) -> T:
        pass

    @abstractmethod
    def generate_structured_stream(
        self,
        model: str,
        contents: Any,
        schema: type[T],
        thinking_level: str | None = None,
        thinking_budget: int | None = None,
        on_thought_chunk: Callable[[str], None] | None = None,
    ) -> T:
        pass

    @abstractmethod
    def list_available_models(self) -> list[str]:
        pass

    @abstractmethod
    def list_thinking_levels(self) -> list[str]:
        pass

    @abstractmethod
    def supports_thinking(self, model: str) -> bool:
        pass

    def refresh_config(self) -> None:
        """Hook for hot-swappable settings applied without restart. No-op by default."""
        pass
