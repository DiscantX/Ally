"""
Main execution entrypoint for running the voice companion package.
Supports optional --loopback CLI flag for WASAPI audio loopback & AEC.
"""

import os
import sys
import argparse
import asyncio
from google import genai

from .config import MODEL_ID
from .player import AudioPlayer
from .recognizer import SpeechRecognizer
from .plugins.loopback.plugin import LoopbackPluginManager
from .companion import GameCompanion
from .orchestrator import dual_input_meter_loop, run_with_reconnect


async def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini Live Voice Companion with Optional Game Audio Loopback")
    parser.add_argument("--loopback", action="store_true", help="Enable experimental WASAPI game audio loopback & AEC plugin")
    args = parser.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    client = genai.Client()
    phrase_queue: "asyncio.Queue[str]" = asyncio.Queue()
    player_turn = asyncio.Event()

    loopback_plugin = None
    if args.loopback:
        print("\n[Plugin Enabled]: Initializing WASAPI Game Audio Loopback & AEC...")
        loopback_plugin = LoopbackPluginManager()

    player = AudioPlayer(
        reference_callback=loopback_plugin.get_reference_callback() if loopback_plugin else None
    )
    companion = GameCompanion(client, player, loopback_plugin=loopback_plugin)

    print(f"\n=== Connecting to {MODEL_ID} Live API Stream ===")
    with SpeechRecognizer() as recognizer:
        if loopback_plugin:
            loopback_plugin.start()
        try:
            meter_task = asyncio.create_task(
                dual_input_meter_loop(recognizer, loopback_plugin, phrase_queue, player_turn)
            )
            try:
                await run_with_reconnect(companion, phrase_queue, player_turn)
            except KeyboardInterrupt:
                print("\nExiting stream session...")
            finally:
                meter_task.cancel()
                await asyncio.gather(meter_task, return_exceptions=True)
                player.close()
        finally:
            if loopback_plugin:
                loopback_plugin.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down safely.")
