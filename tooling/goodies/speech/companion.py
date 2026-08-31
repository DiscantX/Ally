"""
GameCompanion class owning the Gemini Live API session.
"""

import asyncio
from typing import Optional
from google import genai
from google.genai import types
import numpy as np
import scipy.signal as signal

from .config import MODEL_ID, CHOSEN_VOICE, SYSTEM_PROMPT, SYNC_TEXT_TO_SPEECH
from .player import AudioPlayer
from .loopback import SystemLoopbackCapture
from .filter import EchoCancellationFilter


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

    async def run(self, phrase_queue: "asyncio.Queue[str]", player_turn: asyncio.Event, loopback_capture: SystemLoopbackCapture) -> None:
        config = self._build_config()
        async with self._client.aio.live.connect(model=self._model_id, config=config) as session:
            if self._session_handle:
                print("=== Connection Re-established! Resuming previous session... ===")
            else:
                print("=== Connection Established! Start speaking into your mic & playing game audio... ===")
            player_turn.set()  # only now is it safe for the mic loop to start prompting
            sender = asyncio.create_task(self._send_loop(session, phrase_queue, player_turn))
            receiver = asyncio.create_task(self._receive_loop(session, player_turn))
            loopback_sender = asyncio.create_task(self._loopback_send_loop(session, loopback_capture))
            try:
                await asyncio.gather(sender, receiver, loopback_sender)
            finally:
                sender.cancel()
                receiver.cancel()
                loopback_sender.cancel()
                await asyncio.gather(sender, receiver, loopback_sender, return_exceptions=True)

    async def _loopback_send_loop(self, session, capture: SystemLoopbackCapture) -> None:
        filter_engine = EchoCancellationFilter(
            sample_rate=16000,
            channels=1
        )
        buffer = np.array([], dtype=np.int16)
        chunk_size_samples = 320  # 20ms micro-bursts at 16kHz

        # DIAGNOSTIC CODE: Track time for periodic end_of_turn force-flush
        last_force_flush_time = asyncio.get_event_loop().time()

        # TEMPORARY CODE: Diagnostic recording of what Gemini hears
        import wave
        temp_wav = wave.open("gemini_hears_test.wav", "wb")
        temp_wav.setnchannels(1)
        temp_wav.setsampwidth(2)
        temp_wav.setframerate(16000)
        temp_bytes_written = 0
        max_temp_bytes = 16000 * 2 * 30  # 30 seconds at 16kHz 16-bit mono

        try:
            while True:
                # DIAGNOSTIC CODE: Every 12 seconds, force-close the turn to make Gemini reply to heard audio
                now_time = asyncio.get_event_loop().time()
                if now_time - last_force_flush_time > 12.0:
                    try:
                        print("\n=== [DIAGNOSTIC]: Force-flushing turn (end_of_turn=True) to test VAD audio reception ===", flush=True)
                        await session.send(end_of_turn=True)
                    except Exception as e:
                        import sys
                        print(f"Error force-flushing turn: {e}", file=sys.stderr)
                    last_force_flush_time = now_time

                # Feed playback reference audio to AEC filter (downmixed & resampled to 16kHz mono)
                ref_chunk = self._player.poll_reference()
                if ref_chunk is not None:
                    if len(ref_chunk.shape) > 1:
                        ref_mono = ref_chunk.mean(axis=1)
                    else:
                        ref_mono = ref_chunk
                    if self._player._samplerate != 16000:
                        num_samples = int(len(ref_mono) * 16000 / self._player._samplerate)
                        ref_mono = signal.resample(ref_mono, num_samples)
                    filter_engine.analyze_reference(ref_mono.astype(np.int16))

                # Poll loopback audio chunk, downmix stereo to mono, resample to 16kHz, and filter echo
                data = capture.poll_audio()
                if data:
                    try:
                        audio_array = np.frombuffer(data, dtype=np.int16)
                        if capture._actual_channels > 1:
                            audio_array = audio_array.reshape(-1, capture._actual_channels).mean(axis=1)

                        if capture._actual_sample_rate != 16000:
                            num_samples = int(len(audio_array) * 16000 / capture._actual_sample_rate)
                            audio_array = signal.resample(audio_array, num_samples)

                        cleaned_array = filter_engine.process_stream(audio_array.astype(np.int16))
                        buffer = np.concatenate((buffer, cleaned_array.astype(np.int16)))

                        # Dispatch in strict 20ms micro-bursts (320 samples each)
                        while len(buffer) >= chunk_size_samples:
                            packet = buffer[:chunk_size_samples]
                            buffer = buffer[chunk_size_samples:]
                            packet_bytes = packet.tobytes()

                            # TEMPORARY CODE: Write to diagnostic wav file
                            if temp_bytes_written < max_temp_bytes:
                                temp_wav.writeframes(packet_bytes)
                                temp_bytes_written += len(packet_bytes)
                                if temp_bytes_written >= max_temp_bytes:
                                    temp_wav.close()
                                    print("\n=== [TEMPORARY DIAGNOSTIC]: Saved 30s audio to `gemini_hears_test.wav` ===")

                            await session.send(
                                input=types.LiveClientRealtimeInput(
                                    audio=types.Blob(
                                        data=packet_bytes,
                                        mime_type="audio/pcm;rate=16000"
                                    )
                                )
                            )
                    except Exception as e:
                        import sys
                        print(f"Error sending filtered loopback audio: {e}", file=sys.stderr)
                await asyncio.sleep(0.005)
        finally:
            try:
                temp_wav.close()
            except Exception:
                pass

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
