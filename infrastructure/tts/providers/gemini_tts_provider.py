"""Gemini TTS provider implementation.

Phase 0 findings (from tools/debug_raw_tts_stream.py):

1. Model compatibility:
   - gemini-3.1-flash-tts-preview: ✅ Works (preferred)
   - gemini-2.5-flash-preview-tts: ✅ Works (fallback)

2. Non-streaming response shape:
   - Response type: `google.genai.types.Interaction`
   - Audio payload path: `response.output_audio.data` (base64 string)
   - MIME type: `audio/l16; rate=24000; channels=1`
   - Sample rate: 24000 Hz (from mime_type)
   - Channels: 1 (from mime_type)

3. Streaming response shape:
   - Event types: `interaction.created`, `interaction.status_update`, `step.start`, `step.delta`, `step.stop`, `interaction.completed`
   - Audio delta path: `event.delta.type == "audio"` then `event.delta.data` (base64 string)
   - Audio chunks: ~1920 bytes decoded per chunk

4. Audio format:
   - Encoding: PCM 16-bit signed integer (L16)
   - Sample rate: 24000 Hz
   - Channels: Mono (1 channel)
"""

from __future__ import annotations

import base64
import random
import time
from typing import Any, Iterator

from google import genai
from google.genai import errors, types
from dotenv import load_dotenv

load_dotenv(override=True)

from infrastructure.tts.base_provider import TTSProvider, RetryableProviderMixin, SynthesizedAudio
from cabinet.configs.config_manager import load_user_config
from infrastructure.logger import log, timed


class GeminiTTSProvider(TTSProvider, RetryableProviderMixin):
    """Gemini TTS provider using google.genai Interactions API."""

    supports_style_direction: bool = True
    supports_streaming: bool = True

    def __init__(
        self,
        client: genai.Client | None = None,
        model: str | None = None,
        voice_name: str | None = None,
        sample_rate: int | None = None,
        max_retries: int = 5,
    ):
        self.client = client if client is not None else genai.Client()
        config = load_user_config()
        speech_cfg = config.get("speech", {})
        self.model = model or speech_cfg.get("tts_model", "gemini-3.1-flash-tts-preview")
        self.default_voice = voice_name or speech_cfg.get("tts_voice", "Kore")
        self.default_sample_rate = sample_rate or int(speech_cfg.get("tts_sample_rate", 24000))
        self.max_retries = max_retries

    def _is_retryable_error(self, error: Exception) -> bool:
        if isinstance(error, (errors.ServerError, errors.ClientError)):
            # 429 rate limit or 5xx server errors are retryable
            if hasattr(error, "code") and error.code in (429, 500, 502, 503, 504):
                return True
            msg = str(error).lower()
            if "resource_exhausted" in msg or "rate limit" in msg or "unavailable" in msg or "deadline" in msg:
                return True
        return False

    def _extract_retry_delay(self, error: Exception) -> float | None:
        try:
            if hasattr(error, "response") and error.response is not None:
                headers = getattr(error.response, "headers", {})
                retry_after = headers.get("retry-after") or headers.get("Retry-After")
                if retry_after:
                    return float(retry_after)
        except Exception:
            pass
        return None

    def _build_speech_config(self, voice_name: str | None) -> list[dict[str, Any]]:
        voice = voice_name or self.default_voice
        return [{"voice": voice}]

    @timed
    def synthesize(
        self,
        text: str,
        voice_name: str | None = None,
        speaking_rate: float | None = None,
    ) -> SynthesizedAudio:
        prompt = text
        if speaking_rate is not None:
            prompt = f"Speak at rate {speaking_rate}: {text}"

        speech_config = self._build_speech_config(voice_name)
        attempt = 0

        while True:
            attempt += 1
            try:
                response = self.client.interactions.create(
                    model=self.model,
                    input=prompt,
                    response_format={"type": "audio"},
                    speech_config=speech_config,
                )

                audio_blob = getattr(response, "output_audio", None)
                if not audio_blob or not getattr(audio_blob, "data", None):
                    raise ValueError("Gemini TTS response did not contain output_audio data")

                b64_data = audio_blob.data
                pcm_bytes = base64.b64decode(b64_data)

                mime_type = getattr(audio_blob, "mime_type", "") or "audio/l16; rate=24000; channels=1"
                sample_rate = self.default_sample_rate
                if "rate=" in mime_type:
                    try:
                        part = [p for p in mime_type.split(";") if "rate=" in p][0]
                        sample_rate = int(part.split("=")[1].strip())
                    except Exception:
                        pass

                return SynthesizedAudio(
                    pcm_data=pcm_bytes,
                    sample_rate=sample_rate,
                    channels=1,
                    sample_width=2,
                )

            except Exception as e:
                if attempt > self.max_retries or not self._is_retryable_error(e):
                    log("Gemini TTS synthesis failed (max retries exceeded or non-retryable): {e}", e=e)
                    raise

                delay = self._extract_retry_delay(e)
                if delay is None:
                    delay = (2 ** attempt) + random.uniform(0, 1)

                log("Gemini TTS error ({e}). Retrying attempt {attempt}/{max_retries} in {delay:.2f}s...", e=e, attempt=attempt, max_retries=self.max_retries, delay=delay)
                time.sleep(delay)

    @timed
    def synthesize_stream(
        self,
        text: str,
        voice_name: str | None = None,
        speaking_rate: float | None = None,
    ) -> Iterator[bytes]:
        prompt = text
        if speaking_rate is not None:
            prompt = f"Speak at rate {speaking_rate}: {text}"

        speech_config = self._build_speech_config(voice_name)
        attempt = 0

        while True:
            attempt += 1
            try:
                stream = self.client.interactions.create(
                    model=self.model,
                    input=prompt,
                    response_format={"type": "audio"},
                    speech_config=speech_config,
                    stream=True,
                )

                for event in stream:
                    delta = getattr(event, "delta", None)
                    if delta and getattr(delta, "type", None) == "audio":
                        audio_b64 = getattr(delta, "data", None)
                        if audio_b64:
                            yield base64.b64decode(audio_b64)
                return

            except Exception as e:
                if attempt > self.max_retries or not self._is_retryable_error(e):
                    log("Gemini TTS stream synthesis failed (max retries exceeded or non-retryable): {e}", e=e)
                    raise

                delay = self._extract_retry_delay(e)
                if delay is None:
                    delay = (2 ** attempt) + random.uniform(0, 1)

                log("Gemini TTS stream error ({e}). Retrying attempt {attempt}/{max_retries} in {delay:.2f}s...", e=e, attempt=attempt, max_retries=self.max_retries, delay=delay)
                time.sleep(delay)
