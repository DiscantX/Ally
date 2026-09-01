"""TTS infrastructure package.

Provides provider-agnostic TTS interfaces and concrete implementations.
"""

from infrastructure.tts.base_provider import TTSProvider, SynthesizedAudio

__all__ = [
    "TTSProvider",
    "SynthesizedAudio",
]
