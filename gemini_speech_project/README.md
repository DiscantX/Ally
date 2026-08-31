# Gemini Live Speech Library (`gemini-live-speech`)

A high-performance, real-time voice-driven AI assistant library for Python. It bridges local offline speech recognition (`Vosk`) with Google's Gemini Live API via WebSockets, featuring gapless audio playback (`sounddevice`) and optional system audio loopback with Acoustic Echo Cancellation (AEC).

---

## Features

- **Real-Time Voice Streaming**: Connect to Gemini Live API models with bidirectional streaming of audio input and output.
- **Local Offline Speech Recognition**: Uses `Vosk` and `sounddevice` to process microphone input locally with zero cloud STT latency.
- **Thinking Pause Utterance Assembly**: Holds finalized Vosk fragments until a configurable thinking pause elapses (`THINKING_PAUSE_SECONDS`), letting speakers pause mid-sentence without being cut off.
- **Gapless Audio Playback**: Continuous callback-driven `sounddevice.OutputStream` with prebuffering and low-latency scheduling.
- **System Audio Loopback & AEC**: Optional WASAPI audio capture (`pyaudiowpatch`) and echo cancellation filtering for capturing game audio or desktop output alongside microphone input.

---

## Installation

```bash
pip install .
```

---

## Quickstart Example

```python
import os
import asyncio
from google import genai
from gemini_speech import (
    GameCompanion,  # or VoiceCompanion
    AudioPlayer,
    SpeechRecognizer,
    run_with_reconnect,
    dual_input_meter_loop,
)

async def main() -> None:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    player = AudioPlayer()
    phrase_queue: asyncio.Queue[str] = asyncio.Queue()
    player_turn = asyncio.Event()
    
    # Optionally pass a custom system prompt directly into the constructor
    custom_prompt = "You are a helpful and concise coding assistant voice."
    companion = GameCompanion(client=client, player=player, system_prompt=custom_prompt)

    with SpeechRecognizer() as recognizer:
        meter_task = asyncio.create_task(
            dual_input_meter_loop(recognizer, None, phrase_queue, player_turn)
        )
        try:
            await run_with_reconnect(companion, phrase_queue, player_turn)
        finally:
            meter_task.cancel()
            await asyncio.gather(meter_task, return_exceptions=True)
            player.close()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## License

MIT License.
