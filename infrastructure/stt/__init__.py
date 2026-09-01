"""STT infrastructure package.

Provides Vosk-based speech-to-text engine components.
"""

from infrastructure.stt.recognizer import SpeechRecognizer
from infrastructure.stt.assembler import UtteranceAssembler

__all__ = [
    "SpeechRecognizer",
    "UtteranceAssembler",
]
