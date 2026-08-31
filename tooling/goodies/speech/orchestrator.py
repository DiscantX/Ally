"""
Orchestration loops for the microphone polling and connection resilience.
"""

import asyncio
import time

from .config import WAVE_WIDTH, WAVE_REFRESH_SECONDS, RECONNECT_DELAY_SECONDS
from .recognizer import SpeechRecognizer
from .assembler import UtteranceAssembler
from .utils import is_meaningful_phrase, polish_phrase, render_wave
from .companion import GameCompanion


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
