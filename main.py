from __future__ import annotations

"""Vertical slice: a continuous turn loop through the pipeline using AllyCore."""

import argparse
import threading
from typing import Any, Optional, TYPE_CHECKING
import time
import sys
import signal

if TYPE_CHECKING:
    from brain.reasoning.core import AllyCore

from infrastructure.logger import log

# Global references for shutdown coordination
_shutdown_in_progress = threading.Event()
_core_instance: Optional[Any] = None
_qt_app_instance: Optional[Any] = None
_overlay_instance: Optional[Any] = None


def shutdown_application() -> None:
    """Performs a clean, coordinated shutdown of the application.
    
    This is the single shared exit path for all termination triggers:
    - Qt GUI close button / window close
    - StatusStrip exit button
    - Terminal Ctrl+C (SIGINT)
    - Headless mode end of loop
    """
    if _shutdown_in_progress.is_set():
        return  # Prevent double-invocation
    
    _shutdown_in_progress.set()
    log("Initiating clean shutdown...", level="info")
    
    # Instant GUI teardown: hide window immediately and unregister shell bounds
    if _overlay_instance is not None:
        try:
            _overlay_instance.add_ally_message("System", "Shutdown in progress...")
            _overlay_instance.hide()
        except Exception as e:
            log("Error hiding overlay during shutdown: {error}", error=str(e), level="warning")

    try:
        from brain.state.shell_bounds_registry import SHELL_BOUNDS
        SHELL_BOUNDS.unregister("prod_overlay")
    except Exception as e:
        log("Error unregistering shell bounds: {error}", error=str(e), level="warning")
    
    # Quit Qt app immediately on the main thread to unblock event loop and destroy GUI instantly
    if _qt_app_instance is not None:
        try:
            _qt_app_instance.quit()
        except Exception as e:
            log("Error quitting Qt app: {e}", e=e, level="error")

    # Run heavy cleanup in background thread so UI disappears instantly,
    # then force-exit process when complete.
    def _background_cleanup() -> None:
        if _core_instance is not None:
            try:
                _core_instance.stop()
                log("Core shutdown complete.", level="info")
            except Exception as e:
                log("Error stopping core: {e}", e=e, level="error")
        
        log("Shutdown complete.", level="info")
        import os
        os._exit(0)

    threading.Thread(target=_background_cleanup, name="ShutdownCleanup", daemon=True).start()


def _handle_sigint(signum: int, frame: Any) -> None:
    """Signal handler for SIGINT (Ctrl+C)."""
    log("Received Ctrl+C (SIGINT). Shutting down gracefully...", level="info")
    try:
        if hasattr(signal, "siginterrupt"):
            signal.siginterrupt(signum, True)
    except Exception as e:
        log("Error setting signal interrupt: {error}", error=str(e), level="warning")
    
    # If Qt app is active, schedule shutdown on the main thread safely via QTimer
    if _qt_app_instance is not None:
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, shutdown_application)
            return
        except Exception as e:
            log("Error with QTimer in signal handler: {error}", error=str(e), level="warning")
    
    shutdown_application()



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
    t_imports = time.perf_counter()
    from PySide6.QtCore import QTimer
    log(f"run_qt_app_with_overlay heavy imports took {time.perf_counter() - t_imports:.5f}s", level="info")

    core_holder: dict[str, Any] = {"core": None}
    message_queue: list[tuple[str, str]] = []

    # Early UI event bindings executed immediately after overlay is shown
    overlay._status_strip.exit_requested.connect(shutdown_application)

    def handle_message_sent(text: str, mode: str) -> None:
        core = core_holder["core"] or _core_instance
        if core is not None:
            core.send_message(text, mode)
        else:
            log("Core not ready yet, queuing message...", level="info")
            message_queue.append((text, mode))
            overlay.add_ally_message("System", f"Message queued (core initializing): {text}")

    overlay._input_bar.message_sent.connect(handle_message_sent)

    def handle_dev_requested() -> None:
        core = core_holder["core"] or _core_instance
        from interfaces.gui_qt.dev.dev_window import DevInspectorWindow
        DevInspectorWindow.get_instance(core, overlay._theme)

    overlay._status_strip.dev_window_requested.connect(handle_dev_requested)

    def _on_core_initialized(loaded_core: AllyCore) -> None:
        log("Core initialization completed, setting up Qt bridge and signals...", level="info")
        try:
            from interfaces.gui_qt.dev.bridge import CoreBridge
            core_holder["core"] = loaded_core
            global _core_instance
            _core_instance = loaded_core
            overlay.set_registry(loaded_core.entity_registry)

            from interfaces.gui_qt.dev.dev_window import DevInspectorWindow
            if DevInspectorWindow._instance is not None:
                DevInspectorWindow._instance.set_core(loaded_core)

            bridge = CoreBridge(loaded_core)
            bridge.chat_message_ready.connect(lambda sender, msg: overlay.add_ally_message(sender, msg))
            bridge.analysis_stream_finalize.connect(lambda analysis: overlay.add_ally_message("Ally", analysis))
            bridge.connection_status_ready.connect(lambda stat: overlay._status_strip.update_connection(stat))

            # Forward any queued messages now that core is ready
            while message_queue:
                q_text, q_mode = message_queue.pop(0)
                loaded_core.send_message(q_text, q_mode)

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
                    from ingestion.collectors.base import RawObservation
                    from PIL import Image
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
            from brain.reasoning.core import AllyCore
            from ingestion.collectors.base import RawObservation
            from PIL import Image
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

    global _core_instance, _qt_app_instance, _overlay_instance
    if getattr(args, "gui_qt", False) or (not getattr(args, "headless", False) and not getattr(args, "gui", False)):
        from PySide6.QtWidgets import QApplication
        from interfaces.gui_qt.prod.overlay_window import ProdOverlayWindow
        app = QApplication(sys.argv)
        _qt_app_instance = app  # Set global reference for shutdown
        overlay = ProdOverlayWindow(registry=None)
        _overlay_instance = overlay  # Set global reference for instant GUI hiding
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
        _core_instance = core  # Set global reference for shutdown
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

# Register SIGINT handler at module import time so it catches Ctrl+C in all entry points (run.py, main.py, etc.)
signal.signal(signal.SIGINT, _handle_sigint)

# Allows main.py to still be run directly if needed during rapid headless testing
if __name__ == "__main__":
    initialize_application()
