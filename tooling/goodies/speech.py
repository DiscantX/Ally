import os
import sys
import json
import asyncio
import queue
import sounddevice as sd
import numpy as np
from vosk import Model, KaldiRecognizer
from google import genai
from google.genai import types

# 1. Initialize the modern GenAI Client
if not os.environ.get("GEMINI_API_KEY"):
    print("Error: GEMINI_API_KEY environment variable not set.")
    sys.exit(1)

client = genai.Client()

# 2. Setup Local Vosk Engine
if not os.path.exists("model"):
    print("Please place your local offline Vosk 'model' folder in this directory.")
    sys.exit(1)
vosk_model = Model("model")
rec = KaldiRecognizer(vosk_model, 16000)

audio_queue = queue.Queue()
playback_queue = asyncio.Queue()
playback_active = asyncio.Event()

def audio_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    audio_queue.put(bytes(indata))

async def audio_speaker_worker():
    """Consumes audio segments from the queue asynchronously to eliminate choppy playback."""
    try:
        while True:
            audio_array = await playback_queue.get()
            playback_active.set()
            # Play the chunk natively without blocking the main network thread
            sd.play(audio_array, samplerate=24000)
            await asyncio.sleep(len(audio_array) / 24000)
            playback_queue.task_done()
            if playback_queue.empty():
                playback_active.clear()
    except asyncio.CancelledError:
        pass

async def handle_audio_and_text_output(session):
    """Monitors incoming channel, cleanly printing text and feeding the audio player worker."""
    first_chunk_received = False
    try:
        async for response in session.receive():
            server_content = getattr(response, 'server_content', None)
            if server_content is None:
                continue
            
            # Print the header only when the model actually starts responding
            if not first_chunk_received:
                print("\n[AI Companion]: ", end="", flush=True)
                first_chunk_received = True

            # Safely parse out text transcriptions
            output_transcription = getattr(server_content, 'output_transcription', None)
            if output_transcription and hasattr(output_transcription, 'text'):
                print(output_transcription.text, end="", flush=True)
                
            model_turn = getattr(server_content, 'model_turn', None)
            if model_turn is None:
                continue

            for part in model_turn.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                    audio_bytes = part.inline_data.data
                    audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                    # Pipe straight to the background audio queue to prevent stuttering
                    await playback_queue.put(audio_array)

            if getattr(server_content, 'turn_complete', False):
                first_chunk_received = False  # Reset header marker for the next turn

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"\n[Playback Monitoring Error]: {e}")

async def main_loop():
    """Ties local mic queue events to the continuous async Live API session."""
    model_id = "gemini-3.1-flash-live-preview"
    
    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=types.Content(
            parts=[types.Part.from_text(text="You are an interactive video game companion. Keep responses under 2 sentences.")]
        ),
        temperature=0.5,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
            )
        )
    )

    print(f"\n=== Connecting to {model_id} Free Live API Stream ===")
    
    async with client.aio.live.connect(model=model_id, config=live_config) as session:
        print("=== Connection Established! Start speaking into your mic... ===")
        
        # Start both the network listening task and the audio playback worker task
        output_task = asyncio.create_task(handle_audio_and_text_output(session))
        speaker_task = asyncio.create_task(audio_speaker_worker())
        
        try:
            while True:
                await asyncio.sleep(0.01)
                
                while not audio_queue.empty():
                    data = audio_queue.get_nowait()
                    
                    if rec.AcceptWaveform(data):
                        result_dict = json.loads(rec.Result())
                        player_phrase = result_dict.get("text", "").strip()
                        
                        # Only forward if the player spoke and the AI companion is done speaking
                        if player_phrase and not playback_active.is_set():
                            print(f"\n[Player]: {player_phrase}")
                            
                            # FIX: Used official send_client_content structure to silence the DeprecationWarning
                            await session.send_client_content(
                                turns=[
                                    types.Content(
                                        role="user",
                                        parts=[types.Part.from_text(text=player_phrase)]
                                    )
                                ],
                                turn_complete=True
                            )
                            
                            # Hard reset Vosk to prevent echoing inputs into subsequent turns
                            rec.Reset()
                            with audio_queue.mutex:
                                audio_queue.queue.clear()

        except KeyboardInterrupt:
            print("\nExiting stream session...")
        finally:
            output_task.cancel()
            speaker_task.cancel()
            await asyncio.gather(output_task, speaker_task, return_exceptions=True)

if __name__ == "__main__":
    stream = sd.RawInputStream(samplerate=16000, blocksize=4000, dtype='int16',
                               channels=1, callback=audio_callback)
    
    with stream:
        try:
            asyncio.run(main_loop())
        except KeyboardInterrupt:
            print("\nShutting down safely.")
