"""
Voice-driven game companion using local Vosk speech recognition and the
Gemini Live API for spoken responses.

Fixes over the previous version:
  * Gapless playback: a single persistent sd.OutputStream, fed by a
    continuously-stitched buffer, replaces the old per-packet sd.play()
    calls (which restarted the audio device on every packet and caused
    the choppiness).
  * Multi-turn responses: session.receive() only yields messages for a
    single turn and then ends, so the receive loop now re-enters it in
    a `while True` instead of listening just once.
"""

import os
import sys
import json
import time
import asyncio
import queue
import threading
from collections import deque
from typing import Optional

import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from google import genai
from google.genai import types

MODEL_ID = "gemini-3.1-flash-live-preview"
CHOSEN_VOICE = "Aoede"
VOSK_MODEL_PATH = "model"
MIC_SAMPLE_RATE = 16000
TTS_SAMPLE_RATE = 24000
SYSTEM_PROMPT = "You Ally, are a young female, excitable, irreverant, interactive video game companion. Keep responses under 2 sentences."

# When True, printed text is throttled to roughly match speech playback
# instead of appearing as fast as the network delivers it. Approximate —
# there's no per-word timestamp linking text to audio in the API — but it
# keeps the transcript from finishing well before the voice does.
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
# instant Vosk does; we wait this long for more speech before committing —
# a cheap stand-in for the acoustic/linguistic "end of utterance" models
# real voice assistants use to make that same call.
THINKING_PAUSE_SECONDS = 0.7

# Filler words stripped out of the final merged phrase before it's sent.
FILLER_WORDS = {"um", "uh", "umm", "uhh", "er", "erm"}

# Terminal mic-activity meter.
WAVE_WIDTH = 20
WAVE_REFRESH_SECONDS = 0.1


def is_meaningful_phrase(phrase: str) -> bool:
    """Filter out likely noise: single words are only accepted if whitelisted.

    Multi-word phrases are always accepted, since background noise rarely
    gets misrecognized as more than one word.
    """
    words = phrase.split()
    if len(words) > 1:
        return True
    return words[0].lower() in SINGLE_WORD_WHITELIST


# Vosk's output is lowercase with no punctuation ("is that death"). Guessing
# a question mark for these leading words covers most spoken questions
# cheaply; anything else defaults to a period.
_QUESTION_STARTERS = {
    "who", "what", "when", "where", "why", "how",
    "is", "are", "am", "was", "were",
    "do", "does", "did",
    "can", "could", "would", "will", "should", "shall",
}


def polish_phrase(phrase: str) -> str:
    """Capitalize and punctuate a raw Vosk transcript.

    Purely cosmetic string handling — strip filler words, capitalize the
    first letter and any standalone "i", then append "?" or "." based on
    the first word. No model call, so it adds no meaningful latency.
    """
    words = phrase.split()
    stripped = [w for w in words if w.lower() not in FILLER_WORDS]
    if stripped:
        words = stripped
    words = ["I" if w == "i" else w for w in words]
    cleaned = " ".join(words)
    cleaned = cleaned[0].upper() + cleaned[1:]
    if words[0].lower() in _QUESTION_STARTERS:
        cleaned += "?"
    else:
        cleaned += "."
    return cleaned


def render_wave(level: float, width: int = WAVE_WIDTH) -> str:
    """Render a simple ASCII amplitude meter for live mic-level display."""
    filled = int(min(1.0, max(0.0, level)) * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


class AudioPlayer:
    """Gapless audio playback via one long-lived, callback-driven output stream.

    Incoming PCM chunks are kept in a deque and only sliced out of the front
    chunk on each callback tick — never copied into one big buffer — so the
    lock the real-time callback needs is only ever held briefly. (An earlier
    version rebuilt the whole buffer with np.concatenate() on every incoming
    chunk; that copy could occasionally still be running when the callback
    needed the lock, causing rare, brief dropouts.) Because the device
    stream is opened exactly once for the whole session, there is also no
    per-chunk startup/teardown overhead, so consecutive chunks play
    back-to-back with no gaps between them.

    Each fresh utterance also waits for `prebuffer_ms` worth of audio to
    accumulate before playback starts, to absorb the initial delay while
    the network catches up. `latency="high"` asks PortAudio for a larger
    device-level buffer, giving brief Python-side scheduling delays more
    headroom to hide in before they become an audible gap.
    """

    def __init__(
        self,
        samplerate: int = TTS_SAMPLE_RATE,
        prebuffer_ms: int = 150,
        latency: str = "high",
    ):
        self._samplerate = samplerate
        self._chunks: "deque[np.ndarray]" = deque()
        self._chunk_offset = 0
        self._buffered_samples = 0
        self._lock = threading.Lock()
        self._playing = threading.Event()
        self._priming = True
        self._prebuffer_samples = int(samplerate * prebuffer_ms / 1000)
        self._stream = sd.OutputStream(
            samplerate=samplerate,
            channels=1,
            dtype="int16",
            blocksize=1024,
            latency=latency,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, outdata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)
        with self._lock:
            if self._priming:
                if self._buffered_samples < self._prebuffer_samples:
                    outdata[:, 0] = 0
                    return
                self._priming = False

            written = 0
            while written < frames and self._chunks:
                chunk = self._chunks[0]
                available_in_chunk = len(chunk) - self._chunk_offset
                take = min(available_in_chunk, frames - written)
                outdata[written:written + take, 0] = chunk[self._chunk_offset:self._chunk_offset + take]
                self._chunk_offset += take
                written += take
                self._buffered_samples -= take
                if self._chunk_offset >= len(chunk):
                    self._chunks.popleft()
                    self._chunk_offset = 0

            if written < frames:
                outdata[written:, 0] = 0

            if self._buffered_samples <= 0:
                self._buffered_samples = 0
                self._playing.clear()
                self._priming = True  # re-arm so the next utterance also gets a prebuffer

    def enqueue(self, audio_array: np.ndarray) -> None:
        """Append a chunk of int16 PCM audio to the continuous playback buffer."""
        with self._lock:
            self._chunks.append(audio_array)
            self._buffered_samples += len(audio_array)
            self._playing.set()

    def is_playing(self) -> bool:
        return self._playing.is_set()

    def buffered_seconds(self) -> float:
        """Seconds of audio currently queued but not yet played — used to
        throttle text reveal when SYNC_TEXT_TO_SPEECH is enabled."""
        with self._lock:
            return self._buffered_samples / self._samplerate

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


class SpeechRecognizer:
    """Wraps a local Vosk model to turn microphone audio into finalized phrases."""

    def __init__(self, model_path: str = VOSK_MODEL_PATH, samplerate: int = MIC_SAMPLE_RATE):
        if not os.path.exists(model_path):
            print(f"Please place your local offline Vosk '{model_path}' folder in this directory.")
            sys.exit(1)
        self._recognizer = KaldiRecognizer(Model(model_path), samplerate)
        self._audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self._level = 0.0  # crude, cosmetic loudness reading for the terminal meter
        self._stream = sd.RawInputStream(
            samplerate=samplerate,
            blocksize=4000,
            dtype="int16",
            channels=1,
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)
        samples = np.frombuffer(indata, dtype=np.int16)
        if len(samples):
            # Not calibrated to anything acoustic — just scaled to look
            # reasonable for typical mic gain and speaking volume.
            self._level = min(1.0, float(np.abs(samples).mean()) / 2000.0)
        self._audio_queue.put(bytes(indata))

    def __enter__(self) -> "SpeechRecognizer":
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stream.stop()
        self._stream.close()

    def reset(self) -> None:
        """Clear buffered audio and recognizer state.

        Call this right after sending a phrase, so the AI's own voice
        played back through the speakers doesn't get picked back up and
        transcribed as if the player said it.
        """
        self._recognizer.Reset()
        with self._audio_queue.mutex:
            self._audio_queue.queue.clear()

    def poll(self) -> Optional[str]:
        """Drain buffered mic audio and return a finalized phrase, if ready."""
        phrase = None
        while not self._audio_queue.empty():
            data = self._audio_queue.get_nowait()
            if self._recognizer.AcceptWaveform(data):
                result = json.loads(self._recognizer.Result())
                text = result.get("text", "").strip()
                if text:
                    phrase = text
        return phrase

    def level(self) -> float:
        """Current mic loudness, roughly 0.0–1.0, for the terminal meter."""
        return self._level


class GameCompanion:
    """Owns the Gemini Live API session: sends player text, streams back audio/text.

    Holds a session-resumption handle across reconnects. The server hands
    out a fresh handle periodically via session_resumption_update messages;
    passing the latest one back in on connect lets a new WebSocket pick the
    conversation back up instead of starting over — handles are valid for
    2 hours after the previous session ended.
    """

    def __init__(self, client: genai.Client, player: AudioPlayer, model_id: str = MODEL_ID):
        self._client = client
        self._model_id = model_id
        self._player = player
        self._session_handle: Optional[str] = None

    def _build_config(self) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=types.Content(parts=[types.Part.from_text(text=SYSTEM_PROMPT)]),
            temperature=0.5,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=CHOSEN_VOICE)
                )
            ),
            session_resumption=types.SessionResumptionConfig(handle=self._session_handle),
        )

    async def run(self, phrase_queue: "asyncio.Queue[str]", player_turn: asyncio.Event) -> None:
        config = self._build_config()
        async with self._client.aio.live.connect(model=self._model_id, config=config) as session:
            if self._session_handle:
                print("=== Connection Re-established! Resuming previous session... ===")
            else:
                print("=== Connection Established! Start speaking into your mic... ===")
            player_turn.set()  # only now is it safe for the mic loop to start prompting
            sender = asyncio.create_task(self._send_loop(session, phrase_queue, player_turn))
            receiver = asyncio.create_task(self._receive_loop(session, player_turn))
            try:
                await asyncio.gather(sender, receiver)
            finally:
                sender.cancel()
                receiver.cancel()
                await asyncio.gather(sender, receiver, return_exceptions=True)

    async def _send_loop(
        self, session, phrase_queue: "asyncio.Queue[str]", player_turn: asyncio.Event
    ) -> None:
        while True:
            phrase = await phrase_queue.get()
            player_turn.clear()  # our turn is over; the AI is about to respond
            await session.send_client_content(
                turns=[types.Content(role="user", parts=[types.Part.from_text(text=phrase)])],
                turn_complete=True,
            )

    async def _reveal_text(self, text: str) -> None:
        if SYNC_TEXT_TO_SPEECH:
            await asyncio.sleep(self._player.buffered_seconds())
        print(text, end="", flush=True)

    async def _receive_loop(self, session, player_turn: asyncio.Event) -> None:
        """Keep listening across every turn, not just the first one.

        session.receive() is scoped to a single model turn: the async
        generator it returns ends once turn_complete fires. To catch
        subsequent turns we have to call it again, so this loops forever.
        """
        while True:
            first_chunk = True
            async for response in session.receive():
                update = getattr(response, "session_resumption_update", None)
                if update and getattr(update, "resumable", False) and getattr(update, "new_handle", None):
                    self._session_handle = update.new_handle

                server_content = getattr(response, "server_content", None)
                if server_content is None:
                    continue

                if first_chunk:
                    print("\n[AI Companion]: ", end="", flush=True)
                    first_chunk = False

                transcription = getattr(server_content, "output_transcription", None)
                if transcription and getattr(transcription, "text", None):
                    await self._reveal_text(transcription.text)

                model_turn = getattr(server_content, "model_turn", None)
                if model_turn:
                    for part in model_turn.parts:
                        if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                            audio_array = np.frombuffer(part.inline_data.data, dtype=np.int16)
                            self._player.enqueue(audio_array)

            if not first_chunk:
                # The turn's text is done streaming; close its line, then wait
                # for the (slower) audio to actually finish playing before
                # handing the prompt back to the player — this also stops the
                # mic from picking up the companion's own voice as input.
                print()
                while self._player.is_playing():
                    await asyncio.sleep(0.05)
                player_turn.set()


class UtteranceAssembler:
    """Buffers Vosk's per-pause finalized fragments into one utterance.

    Vosk finalizes on its own internal silence detection, which cuts a
    player off mid-thought if they pause. This holds each finalized
    fragment and only considers the utterance complete once
    `pause_seconds` has passed with no new fragment — letting the player
    pause to think without being cut off, the same problem real voice
    assistants solve with a trained end-of-utterance model, just handled
    here as a plain timer.
    """

    def __init__(self, pause_seconds: float = THINKING_PAUSE_SECONDS):
        self._pause_seconds = pause_seconds
        self._fragments: list[str] = []
        self._last_fragment_time: Optional[float] = None

    def add_fragment(self, fragment: str) -> None:
        self._fragments.append(fragment)
        self._last_fragment_time = time.monotonic()

    def has_pending(self) -> bool:
        return bool(self._fragments)

    def ready(self) -> bool:
        """True once enough silence has passed since the last fragment."""
        if not self._fragments or self._last_fragment_time is None:
            return False
        return (time.monotonic() - self._last_fragment_time) >= self._pause_seconds

    def flush(self) -> str:
        phrase = " ".join(self._fragments)
        self._fragments.clear()
        self._last_fragment_time = None
        return phrase


async def microphone_loop(
    recognizer: SpeechRecognizer,
    phrase_queue: "asyncio.Queue[str]",
    player_turn: asyncio.Event,
) -> None:
    """Poll the recognizer and forward complete utterances, but only during
    the player's turn (player_turn is held by GameCompanion between AI turns).

    Shows "[Player]: " plus a live mic-level meter while waiting, so there's
    visible confirmation the mic is being heard even during a thinking
    pause. The meter line is overwritten in place with the recognized text
    once an utterance is judged complete (see UtteranceAssembler); noise
    that never becomes a meaningful phrase is discarded silently.
    """
    prompt_shown = False
    last_wave_draw = 0.0
    assembler = UtteranceAssembler()

    while True:
        await asyncio.sleep(0.01)

        if not player_turn.is_set():
            prompt_shown = False
            assembler = UtteranceAssembler()  # drop any stray partial from before
            continue

        if not prompt_shown:
            print("\n[Player]: ", end="", flush=True)
            prompt_shown = True

        fragment = recognizer.poll()
        if fragment:
            assembler.add_fragment(fragment)

        if assembler.ready():
            phrase = assembler.flush()
            if is_meaningful_phrase(phrase):
                phrase = polish_phrase(phrase)
                # Pad over any leftover meter characters on this line.
                print(f"\r[Player]: {phrase}" + " " * (WAVE_WIDTH + 2))
                player_turn.clear()  # Clear immediately upon phrase commit to prevent race
                await phrase_queue.put(phrase)
                recognizer.reset()
                # Wait for the turn to actually change hands before looping
                # back — otherwise a stray meter redraw can sneak in during
                # the brief window before _send_loop clears player_turn.
                while player_turn.is_set():
                    await asyncio.sleep(0.01)
            continue

        now = time.monotonic()
        if now - last_wave_draw >= WAVE_REFRESH_SECONDS:
            print(f"\r[Player]: {render_wave(recognizer.level())}", end="", flush=True)
            last_wave_draw = now


RECONNECT_DELAY_SECONDS = 2


async def run_with_reconnect(
    companion: GameCompanion, phrase_queue: "asyncio.Queue[str]", player_turn: asyncio.Event
) -> None:
    """Keep the Live API session alive across drops (e.g. the server closing
    an idle connection). companion.run() raises when the session ends for
    any reason; catch that here and just reconnect instead of crashing.
    """
    while True:
        player_turn.clear()  # don't let the mic loop prompt while disconnected
        try:
            await companion.run(phrase_queue, player_turn)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"\n[Connection Lost]: {e}\nReconnecting in {RECONNECT_DELAY_SECONDS}s...")
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)


async def main() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    client = genai.Client()
    player = AudioPlayer()
    phrase_queue: "asyncio.Queue[str]" = asyncio.Queue()
    player_turn = asyncio.Event()  # shared turn-token: prevents the mic and
    # AI-response loops from printing to the terminal at the same time
    companion = GameCompanion(client, player)

    print(f"\n=== Connecting to {MODEL_ID} Live API Stream ===")
    with SpeechRecognizer() as recognizer:
        mic_task = asyncio.create_task(microphone_loop(recognizer, phrase_queue, player_turn))
        try:
            await run_with_reconnect(companion, phrase_queue, player_turn)
        except KeyboardInterrupt:
            print("\nExiting stream session...")
        finally:
            mic_task.cancel()
            await asyncio.gather(mic_task, return_exceptions=True)
            player.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down safely.")