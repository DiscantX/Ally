"""Vertical slice: a continuous turn loop through the pipeline using AllyCore."""

import argparse
from typing import Any
import time
import sys

from infrastructure.logger import log

# NOTE: STATE_LOCK has been removed. All thread synchronization should use
# AllyCore.state_lock or appropriate component-specific locks.
# This global lock was confusing and not consistently used.
# See brain/reasoning/core.py for the proper locking discipline.


class TerminalStreamPrinter:
    """Best-effort live terminal printer for one streaming text field,
    with an ANSI-based visual reset for mid-stream retries.

    LIMITATION, stated explicitly rather than silently: this only tracks
    explicit '\n' characters it has printed. If the terminal soft-wraps
    a long unbroken line (no '\n' in it) because it's wider than the
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
    parser.add_argument(
        "--gui-qt",
        action="store_true",
        help="Launch the standalone PySide6 Ally GUI overlay.",
    )
    return parser.parse_args()


def run_qt_app_with_overlay(app: Any, overlay: Any) -> None:
    """Runs the Qt application with an already-instantiated and shown ProdOverlayWindow."""
    args = parse_args()
    from PySide6.QtCore import QTimer
    from gui_qt.dev.dev_window import DevInspectorWindow
    from gui_qt.dev.bridge import CoreBridge
    from brain.reasoning.core import AllyCore
    from ingestion.collectors.base import RawObservation
    from PIL import Image

    core_holder: dict[str, Any] = {"core": None}

    def _on_core_initialized(loaded_core: AllyCore) -> None:
        log("Core initialization completed, setting up Qt bridge and signals...", level="info")
        try:
            core_holder["core"] = loaded_core
            overlay.set_registry(loaded_core.entity_registry)

            bridge = CoreBridge(loaded_core)
            bridge.chat_message_ready.connect(lambda sender, msg: overlay.add_ally_message(sender, msg))
            bridge.analysis_stream_finalize.connect(lambda analysis: overlay.add_ally_message("Ally", analysis))
            bridge.connection_status_ready.connect(lambda stat: overlay._status_strip.update_connection(stat))

            overlay._status_strip.dev_window_requested.connect(
                lambda: DevInspectorWindow.get_instance(loaded_core, overlay._theme)
            )
            overlay._input_bar.message_sent.connect(
                lambda text, mode: loaded_core.send_message(text, mode)
            )

            # Voice output: construct VoiceOutputController if enabled in config.
            # VoiceInputController is already owned by ProdOverlayWindow (wired in overlay_window.py).
            try:
                from infrastructure.tts.providers.gemini_tts_provider import GeminiTTSProvider
                from infrastructure.tts.audio_player import AudioPlayer
                from brain.reasoning.voice_output_controller import VoiceOutputController
                from cabinet.configs.config_manager import load_user_config

                config = load_user_config() or {}
                if config.get("voice_output_enabled", False):
                    tts_provider = GeminiTTSProvider()
                    audio_player = AudioPlayer()
                    voice_output = VoiceOutputController(tts_provider, audio_player, enabled=True)
                    voice_output.attach(loaded_core)
                    log("VoiceOutputController attached to AllyCore.", level="info")
            except Exception as exc:
                log("Could not initialise VoiceOutputController: {}", exc, level="warning")

            overlay.add_ally_message("System", "Ally is online and ready!")
            log("ProdOverlayWindow bridge signals connected successfully.", level="info")

            if args.image:
                def _run_single() -> None:
                    log("Executing single-shot image observation turn...")
                    observation = RawObservation(image=Image.open(str(args.image)))
                    loaded_core.run_turn(observation)
                    loaded_core.stop()
                threading.Thread(target=_run_single, daemon=True).start()
            else:
                log("Spawning AllyCore.run_loop background thread...", level="info")
                threading.Thread(target=loaded_core.run_loop, daemon=True).start()
        except Exception as e:
            log("Error in _on_core_initialized: {e}", e=e, level="error")

    def _async_init() -> None:
        log("Starting asynchronous AllyCore instantiation...", level="info")
        try:
            loaded_core = AllyCore(
                config_path=args.config,
                game_id=args.game,
                image_path=args.image,
            )
            log("AllyCore instantiated. Calling initialize_run()...", level="info")
            loaded_core.initialize_run()
            log("AllyCore.initialize_run() finished successfully. Scheduling _on_core_initialized...", level="info")
            QTimer.singleShot(0, overlay, lambda: _on_core_initialized(loaded_core))
        except Exception as e:
            log("Exception in _async_init: {e}", e=e, level="error")
            import traceback
            log("Traceback:\n{tb}", tb=traceback.format_exc(), level="error")
            err_msg = str(e)
            QTimer.singleShot(0, overlay, lambda: overlay.add_ally_message("System", f"Initialization error: {err_msg}"))

    # Defer async init slightly via QTimer so the event loop spins and renders/makes the window responsive/draggable immediately
    QTimer.singleShot(50, overlay, lambda: threading.Thread(target=_async_init, daemon=True).start())
    app.exec()


def initialize_application() -> None:
    """Application entry point invoked cleanly after splash screen processes terminate or in headless/tkinter modes."""
    args = parse_args()

    if getattr(args, "gui_qt", False) or (not getattr(args, "headless", False) and not getattr(args, "gui", False)):
        from PySide6.QtWidgets import QApplication
        from gui_qt.prod.overlay_window import ProdOverlayWindow
        app = QApplication(sys.argv)
        overlay = ProdOverlayWindow(registry=None)
        overlay.show()
        overlay.add_ally_message("System", "Initializing Ally & Perception pipeline...")
        run_qt_app_with_overlay(app, overlay)
    else:
        from brain.reasoning.core import AllyCore
        from ingestion.collectors.base import RawObservation
        from PIL import Image

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
            thinking_printer = TerminalStreamPrinter(prefix="\nAlly (thinking): ")

            core.on_thinking_stream_begin.connect(thinking_printer.begin)
            core.on_thinking_stream_chunk.connect(thinking_printer.chunk)
            core.on_thinking_stream_reset.connect(thinking_printer.reset)
            core.on_thinking_stream_finalize.connect(lambda: print("", flush=True))

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
