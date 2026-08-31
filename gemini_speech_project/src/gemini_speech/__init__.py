"""
Gemini Live Speech Companion Library (`gemini_speech`)
"""

from .config import (
    MODEL_ID,
    CHOSEN_VOICE,
    VOSK_MODEL_PATH,
    MIC_SAMPLE_RATE,
    TTS_SAMPLE_RATE,
    SYSTEM_PROMPT,
    SYNC_TEXT_TO_SPEECH,
    SINGLE_WORD_WHITELIST,
    THINKING_PAUSE_SECONDS,
    FILLER_WORDS,
    WAVE_WIDTH,
    WAVE_REFRESH_SECONDS,
    RECONNECT_DELAY_SECONDS,
)
from .assembler import UtteranceAssembler
from .player import AudioPlayer
from .recognizer import SpeechRecognizer
from .companion import GameCompanion, VoiceCompanion
from .orchestrator import dual_input_meter_loop, run_with_reconnect
from .utils import is_meaningful_phrase, polish_phrase, render_wave

__all__ = [
    "MODEL_ID",
    "CHOSEN_VOICE",
    "VOSK_MODEL_PATH",
    "MIC_SAMPLE_RATE",
    "TTS_SAMPLE_RATE",
    "SYSTEM_PROMPT",
    "SYNC_TEXT_TO_SPEECH",
    "SINGLE_WORD_WHITELIST",
    "THINKING_PAUSE_SECONDS",
    "FILLER_WORDS",
    "WAVE_WIDTH",
    "WAVE_REFRESH_SECONDS",
    "RECONNECT_DELAY_SECONDS",
    "UtteranceAssembler",
    "AudioPlayer",
    "SpeechRecognizer",
    "GameCompanion",
    "VoiceCompanion",
    "dual_input_meter_loop",
    "run_with_reconnect",
    "is_meaningful_phrase",
    "polish_phrase",
    "render_wave",
]
