"""
Configuration constants and settings for the voice-driven game companion.
"""

MODEL_ID = "gemini-3.1-flash-live-preview"
CHOSEN_VOICE = "Aoede"
VOSK_MODEL_PATH = "model"
MIC_SAMPLE_RATE = 16000
TTS_SAMPLE_RATE = 24000
SYSTEM_PROMPT = "You Ally, are a young female, excitable, irreverant, interactive video game companion. Keep responses under 2 sentences."

# When True, printed text is throttled to roughly match speech playback
# instead of appearing as fast as the network delivers it.
SYNC_TEXT_TO_SPEECH = True

# Short utterances Vosk sometimes mishears from background noise (e.g. "huh",
# "uh") get dropped unless they're on this list of legitimate one-word replies.
SINGLE_WORD_WHITELIST = {
    "hello", "hi", "hey", "goodbye", "bye",
    "yes", "no", "okay", "ok",
    "wait", "stop", "help", "run", "go",
}

# Vosk finalizes on its own internal pause detection, which is too eager for
# a player who pauses mid-sentence to think. We don't finalize a phrase the
# instant Vosk does; we wait this long for more speech before committing.
THINKING_PAUSE_SECONDS = 0.7

# Filler words stripped out of the final merged phrase before it's sent.
FILLER_WORDS = {"um", "uh", "umm", "uhh", "er", "erm"}

# Terminal mic-activity meter.
WAVE_WIDTH = 20
WAVE_REFRESH_SECONDS = 0.1

# Reconnect delay for the Gemini Live API stream
RECONNECT_DELAY_SECONDS = 2
