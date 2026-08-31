"""
Main execution entrypoint for running the voice companion package.
"""

import os
import sys
import asyncio
from google import genai

from .config import MODEL_ID
from .player import AudioPlayer
from .recognizer import SpeechRecognizer
from .companion import GameCompanion
from .orchestrator import microphone_loop, run_with_reconnect


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
