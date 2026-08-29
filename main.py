"""Vertical slice: a continuous turn loop through the pipeline using AllyCore."""

import argparse
import threading
from PIL import Image
import time

from brain.reasoning.core import AllyCore
from ingestion.collectors.base import RawObservation
from infrastructure.logger import log

STATE_LOCK = threading.Lock()


class TerminalStreamPrinter:
    """Best-effort live terminal printer for one streaming text field,
    with an ANSI-based visual reset for mid-stream retries.

    LIMITATION, stated explicitly rather than silently: this only tracks
    explicit '\\n' characters it has printed. If the terminal soft-wraps
    a long unbroken line (no '\\n' in it) because it's wider than the
    terminal's column count, reset() will NOT correctly clear the
    wrapped portion -- that would require querying the terminal's actual
    column width, which this does not do. This is a best-effort
    convenience for the common case (a retry mid-sentence), not a
    robust terminal UI framework. Acceptable given the person explicitly
    said "if it is easy enough" for this specific piece.
    """

    def __init__(self, prefix: str):
        self.prefix = prefix
        self._newline_count = 0

    def begin(self) -> None:
        print(self.prefix, end="", flush=True)
        self._newline_count = 0

    def chunk(self, text: str) -> None:
        print(text, end="", flush=True)
        self._newline_count += text.count("\n")

    def reset(self) -> None:
        for _ in range(self._newline_count):
            print("\033[1A\033[2K", end="")
        print("\r\033[2K", end="")
        print(self.prefix, end="", flush=True)
        self._newline_count = 0

    def finalize(self, final_text: str) -> None:
        """Reprints final_text cleanly regardless of what was already
        shown -- correcting after-the-fact in a terminal can't be done
        as a text diff the way the GUI's Text widget allows, so this
        just clears and reprints once, which is cheap and only visibly
        matters in the rare drift case."""
        self.reset()
        print(final_text, flush=True)


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
        core.on_status_update.connect(lambda screen, event: None)
        core.on_state_summary.connect(lambda summary: log("Summary:\n{summary}", summary=summary))
        core.on_prompt_update.connect(lambda prompt: None)
        core.on_chat_message.connect(lambda sender, msg: log("{sender}: {msg}", sender=sender, msg=msg))
        core.on_connection_status.connect(lambda conn: log("Connection: {conn}", conn=conn))

        analysis_printer = TerminalStreamPrinter(prefix="\nAlly: ")
        chat_printer = TerminalStreamPrinter(prefix="\nAlly (chat): ")

        core.on_analysis_stream_begin.connect(analysis_printer.begin)
        core.on_analysis_stream_chunk.connect(analysis_printer.chunk)
        core.on_analysis_stream_reset.connect(analysis_printer.reset)
        core.on_analysis_stream_finalize.connect(lambda text: analysis_printer.finalize(text))

        core.on_chat_stream_begin.connect(chat_printer.begin)
        core.on_chat_stream_chunk.connect(chat_printer.chunk)
        core.on_chat_stream_reset.connect(chat_printer.reset)
        core.on_chat_stream_finalize.connect(lambda text: chat_printer.finalize(text))

        if args.image:
            observation = RawObservation(image=Image.open(args.image))
            core.run_turn(observation)
            core.stop()
        else:
            core.run_loop()

# Allows main.py to still be run directly if needed during rapid headless testing
if __name__ == "__main__":
    initialize_application()
