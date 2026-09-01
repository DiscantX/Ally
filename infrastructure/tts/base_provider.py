"""Provider-agnostic base interface, content types, and retry mixin for TTS integrations.

This module contains zero vendor SDK imports (no google.genai, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import re
from typing import Iterator

from infrastructure.logger import log


@dataclass
class SynthesizedAudio:
    """Raw PCM audio data with format metadata.

    Attributes:
        pcm_data: Raw PCM bytes (16-bit signed, little-endian).
        sample_rate: Samples per second (Hz).
        channels: Number of audio channels (1 = mono, 2 = stereo).
        sample_width: Bytes per sample (2 for 16-bit).
    """

    pcm_data: bytes
    sample_rate: int
    channels: int
    sample_width: int = 2  # 16-bit

    def __post_init__(self) -> None:
        if self.sample_width != 2:
            raise ValueError(f"Only 16-bit audio is supported, got sample_width={self.sample_width}")

    @property
    def duration_seconds(self) -> float:
        """Return audio duration in seconds (approximate, ignores header)."""
        bytes_per_sample = self.channels * self.sample_width
        if bytes_per_sample == 0:
            return 0.0
        return len(self.pcm_data) / bytes_per_sample / self.sample_rate


class RetryableProviderMixin(ABC):
    """Generic retry-with-backoff scaffolding for TTS providers.

    Reusable across providers (GeminiTTSProvider, etc.) that need consistent
    retry behavior with exponential backoff.
    """

    @abstractmethod
    def _is_retryable_error(self, error: Exception) -> bool:
        """Return True if the error is transient and safe to retry."""
        pass

    @abstractmethod
    def _extract_retry_delay(self, error: Exception) -> float | None:
        """Extract retry delay from error response, or None for default backoff."""
        pass


def _naive_sentence_split(text: str) -> list[str]:
    """Split text into sentences using simple punctuation detection.

    KNOWN LIMITATIONS:
    - Will incorrectly split on periods in abbreviations (e.g., "Dr.", "U.S.A.")
    - Will incorrectly split on decimals (e.g., "3.14", "v2.0")
    - Will incorrectly split on ellipsis-style "..." sequences
    - Single-character sentences may result from these issues

    For production use, consider a proper NLP-based sentence tokenizer
    (e.g., spaCy, NLTK, or a regex-based splitter with abbreviation handling).
    """
    # Split on sentence-ending punctuation followed by whitespace or end of string.
    # Common sentence boundaries: . ! ?
    # We don't include ... in the split pattern to avoid breaking ellipsis.
    pattern = r'(?<=[.!?])\s+'
    sentences = re.split(pattern, text.strip())

    # Filter out empty strings that may result from multiple spaces or trailing punctuation.
    return [s.strip() for s in sentences if s.strip()]


class TTSProvider(ABC):
    """Abstract base class for all TTS providers (Gemini, etc.).

    Class Attributes:
        supports_style_direction: Whether this provider supports SSML-style
            voice/style parameters. If True, providers should accept optional
            voice_name and speaking_rate kwargs in synthesize().
        supports_streaming: Whether this provider implements streaming audio
            generation (chunked synthesis for lower latency).
    """

    supports_style_direction: bool = False
    supports_streaming: bool = False

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_name: str | None = None,
        speaking_rate: float | None = None,
    ) -> SynthesizedAudio:
        """Synthesize speech for the given text.

        Args:
            text: Text to synthesize. For multi-sentence text, the provider
                may process it as a single unit.
            voice_name: Optional voice identifier (provider-specific).
                Only used if supports_style_direction is True.
            speaking_rate: Optional speaking rate multiplier (e.g., 1.0 = normal,
                0.8 = slower, 1.2 = faster). Only used if supports_style_direction
                is True.

        Returns:
            SynthesizedAudio with PCM data and format metadata.

        Raises:
            TTSError: If synthesis fails.
        """
        pass

    def synthesize_stream(
        self,
        text: str,
        voice_name: str | None = None,
        speaking_rate: float | None = None,
    ) -> Iterator[SynthesizedAudio]:
        """Stream synthesized audio chunks sentence-by-sentence.

        Default implementation splits text into sentences using naive punctuation
        detection and yields each sentence's audio as a separate SynthesizedAudio.

        Override this method for streaming-specific optimizations (e.g., Gemini's
        chunked delta events).

        KNOWN LIMITATION: The naive sentence splitter may incorrectly break on
        abbreviations (Dr., U.S.A.), decimals (3.14), and ellipses (...). Consider
        overriding with a provider-specific tokenizer for production use.

        Args:
            text: Text to synthesize and stream.
            voice_name: Optional voice identifier (provider-specific).
            speaking_rate: Optional speaking rate multiplier.

        Yields:
            SynthesizedAudio chunks, typically one per sentence.

        Raises:
            TTSError: If synthesis fails for any chunk.
        """
        sentences = _naive_sentence_split(text)
        for sentence in sentences:
            if sentence:
                yield self.synthesize(
                    text=sentence,
                    voice_name=voice_name,
                    speaking_rate=speaking_rate,
                )

    def refresh_config(self) -> None:
        """Hook for hot-swappable settings applied without restart. No-op by default."""
        pass


class TTSError(Exception):
    """Base exception for TTS-related errors."""

    pass
