# =====================================================================
#     ___    __      __  __  __
#    /   |  / /     / /  \ \/ /
#   / /| | / /     / /    \  / 
#  / ___ |/ /___  / /___  / /  
# /_/  |_/_____/ /_____/ /_/   
#   ALLY • Intelligent Game Companion
#   Autonomous Live Loop for Your Games
# =====================================================================

import sys
# Lower GIL switch interval for UI responsiveness during startup
sys.setswitchinterval(0.001)

import time
from interfaces.visuals.header import run_header_splash
from infrastructure.logger import log, timer

MODULE_NAME = "Run"

@timer
def initialize_and_run(main_module):
    is_headless = "--headless" in sys.argv

    if is_headless:
        log("Initializing headless application...")
        main_module.initialize_application()
    else:
        # Early Qt GUI bootstrapping design principle:
        # Instantiate and show QApplication and ProdOverlayWindow at absolute earliest point,
        # before importing heavy perception/core modules or loading configurations/models.
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from interfaces.gui_qt.prod.overlay_window import ProdOverlayWindow

        app = QApplication(sys.argv)
        overlay = ProdOverlayWindow(registry=None)
        overlay.show()
        overlay.add_ally_message("System", "Initializing Ally & Perception pipeline...")

        QTimer.singleShot(0, lambda: log(
            "GUI event loop running, starting core pipeline initialization...",
            level="info",
        ))

        # Run async core initialization after GUI is visible on screen
        main_module.run_qt_app_with_overlay(app, overlay)

def main():
    # 1. Call run_header_splash() as absolute first call in run.py
    # Add timing instrumentation around run_header_splash()
    t0 = time.perf_counter()
    main_module = run_header_splash()
    elapsed = time.perf_counter() - t0
    log(f"run_header_splash() completed in {elapsed:.5f}s", level="info")
    initialize_and_run(main_module)

if __name__ == "__main__":
    main()
