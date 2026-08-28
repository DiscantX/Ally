"""Vertical slice: a continuous turn loop through the pipeline using AllyCore."""

import argparse
import threading
from PIL import Image
import time

from brain.reasoning.core import AllyCore
from ingestion.collectors.base import RawObservation
from infrastructure.logger import log

STATE_LOCK = threading.Lock()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ally vertical slice runner.")
    parser.add_argument(
        "image", nargs="?",
        help="Path to a single image file -- back-compat single-shot mode, no loop.",
    )
    parser.add_argument(
        "--game",
        help="game_id to run (e.g. 'ftl'). Looks up configs/<game_id>/config.json, "
             "auto-creating it from the currently focused window if it doesn't exist yet. "
             "Omit entirely to derive game_id from whatever window is focused right now.",
    )
    parser.add_argument(
        "--config",
        help="Explicit path to a config.json. Overrides --game entirely -- no "
             "auto-create, the file must already exist.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the standalone Ally GUI overlay.",
    )
    return parser.parse_args()


def initialize_application():
    """Application entry point invoked cleanly after splash screen processes terminate."""
    args = parse_args()

    core = AllyCore(
        config_path=args.config,
        game_id=args.game,
        image_path=args.image,
    )
    core.initialize_run()

    if args.gui:
        from interfaces.gui.tkinter_app import AllyOverlay
        gui_app = AllyOverlay(core=core)
        gui_app.set_connection_status(True)

        if args.image:
            observation = RawObservation(image=Image.open(args.image))
            core.run_turn(observation)
            core.stop()
        else:
            import threading
            threading.Thread(target=core.run_loop, daemon=True).start()

        gui_app.mainloop()
    else:
        # Headless terminal mode
        core.on_status_update = lambda screen, event: None
        core.on_state_summary = lambda summary: log("Summary:\n{summary}", summary=summary)
        core.on_prompt_update = lambda prompt: None
        core.on_feedback = lambda feedback: log("Feedback:\n{feedback}", feedback=feedback)
        core.on_chat_message = lambda sender, msg: log("{sender}: {msg}", sender=sender, msg=msg)
        core.on_connection_status = lambda conn: log("Connection: {conn}", conn=conn)

        if args.image:
            observation = RawObservation(image=Image.open(args.image))
            core.run_turn(observation)
            core.stop()
        else:
            core.run_loop()

# Allows main.py to still be run directly if needed during rapid headless testing
if __name__ == "__main__":
    initialize_application()
