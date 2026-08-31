"""
GameCompanion class owning the Gemini Live API session.
"""

import asyncio
from typing import Optional
from google import genai
from google.genai import types
import numpy as np

from .config import MODEL_ID, CHOSEN_VOICE, SYSTEM_PROMPT, SYNC_TEXT_TO_SPEECH
from .player import AudioPlayer
from .plugins.loopback.plugin import LoopbackPluginManager


class GameCompanion:
    """Owns the Gemini Live API session: sends player text, streams back audio/text.

    Holds a session-resumption handle across reconnects. The server hands
    out a fresh handle periodically via session_resumption_update messages;
    passing the latest one back in on connect lets a new WebSocket pick the
    conversation back up instead of starting over — handles are valid for
    2 hours after the previous session ended.
    """

    def __init__(
        self,
        client: genai.Client,
        player: AudioPlayer,
        model_id: str = MODEL_ID,
        loopback_plugin: Optional[LoopbackPluginManager] = None,
    ):
        self._client = client
        self._model_id = model_id
        self._player = player
        self._loopback_plugin = loopback_plugin
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

    async def run(
        self,
        phrase_queue: "asyncio.Queue[str]",
        player_turn: asyncio.Event,
    ) -> None:
        config = self._build_config()
        async with self._client.aio.live.connect(model=self._model_id, config=config) as session:
            if self._session_handle:
                print("=== Connection Re-established! Resuming previous session... ===")
            else:
                print("=== Connection Established! Start speaking into your mic & playing game audio... ===")
            player_turn.set()  # only now is it safe for the mic loop to start prompting
            sender = asyncio.create_task(self._send_loop(session, phrase_queue, player_turn))
            receiver = asyncio.create_task(self._receive_loop(session, player_turn))

            tasks = [sender, receiver]
            if self._loopback_plugin:
                loopback_sender = asyncio.create_task(self._loopback_plugin.stream_loop(session, self._player))
                tasks.append(loopback_sender)

            try:
                await asyncio.gather(*tasks)
            finally:
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

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
