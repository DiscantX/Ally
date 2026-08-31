"""
Orchestration loops for microphone polling, game audio loopback metering, and connection resilience.
"""

import asyncio
import time
import sys
from typing import Optional

from .config import WAVE_WIDTH, WAVE_REFRESH_SECONDS, RECONNECT_DELAY_SECONDS
from .recognizer import SpeechRecognizer
from .plugins.loopback.plugin import LoopbackPluginManager
from .assembler import UtteranceAssembler
from .utils import is_meaningful_phrase, polish_phrase, render_wave
from .companion import GameCompanion


async def dual_input_meter_loop(
    recognizer: SpeechRecognizer,
    loopback_plugin: Optional[LoopbackPluginManager],
    phrase_queue: "asyncio.Queue[str]",
    player_turn: asyncio.Event,
) -> None:
    """Manages dual live ASCII meters for [Player] mic and optional [Audio] game loopback during turns.

    Renders:
        [Player]: [####----------------]
        [Audio]:  [#######------------]
    Clears and resets cleanly upon turn transitions and phrase commits.
    """
    assembler = UtteranceAssembler()
    prompt_shown = False
    last_wave_draw = 0.0

    while True:
        await asyncio.sleep(0.01)

        if not player_turn.is_set():
            if prompt_shown:
                # Clear meter lines when turn switches to AI
                if loopback_plugin:
                    sys.stdout.write("\033[1A\r" + " " * (WAVE_WIDTH + 12) + "\n\r" + " " * (WAVE_WIDTH + 12) + "\r")
                else:
                    sys.stdout.write("\r" + " " * (WAVE_WIDTH + 12) + "\r")
                sys.stdout.flush()
                prompt_shown = False
            assembler = UtteranceAssembler()
            continue

        if not prompt_shown:
            if loopback_plugin:
                print("\n[Player]: \n[Audio]:  ", end="", flush=True)
            else:
                print("\n[Player]: ", end="", flush=True)
            prompt_shown = True

        fragment = recognizer.poll()
        if fragment:
            assembler.add_fragment(fragment)

        if assembler.ready():
            phrase = assembler.flush()
            if is_meaningful_phrase(phrase):
                phrase = polish_phrase(phrase)
                # Overwrite lines with finalized phrase
                if loopback_plugin:
                    sys.stdout.write("\033[1A\r[Player]: " + phrase + " " * (WAVE_WIDTH + 2) + "\n")
                    sys.stdout.write(" " * (WAVE_WIDTH + 12) + "\r")
                else:
                    sys.stdout.write("\r[Player]: " + phrase + " " * (WAVE_WIDTH + 2) + "\n")
                sys.stdout.flush()
                player_turn.clear()
                await phrase_queue.put(phrase)
                recognizer.reset()
                prompt_shown = False
                while player_turn.is_set():
                    await asyncio.sleep(0.01)
            continue

        now = time.monotonic()
        if now - last_wave_draw >= WAVE_REFRESH_SECONDS:
            mic_wave = render_wave(recognizer.level())
            if loopback_plugin:
                audio_wave = render_wave(loopback_plugin.level())
                sys.stdout.write(f"\033[1A\r[Player]: {mic_wave}\n\r[Audio]:  {audio_wave}")
            else:
                sys.stdout.write(f"\r[Player]: {mic_wave}")
            sys.stdout.flush()
            last_wave_draw = now


async def run_with_reconnect(
    companion: GameCompanion,
    phrase_queue: "asyncio.Queue[str]",
    player_turn: asyncio.Event,
) -> None:
    """Keep the Live API session alive across drops (e.g. server closing idle connection)."""
    while True:
        player_turn.clear()
        try:
            await companion.run(phrase_queue, player_turn)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"\n[Connection Lost]: {e}\nReconnecting in {RECONNECT_DELAY_SECONDS}s...")
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
