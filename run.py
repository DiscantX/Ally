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
from interfaces.visuals.header import run_header_splash
from infrastructure.logger import log, timer

MODULE_NAME = "Run"

@timer
def initialize_and_run(main_module):
    is_headless = "--headless" in sys.argv
    is_tkinter = "--gui" in sys.argv

    if is_headless or is_tkinter:
        log("Initializing headless or tkinter application...")
        main_module.initialize_application()
    else:
        # Early Qt GUI bootstrapping design principle:
        # Instantiate and show QApplication and ProdOverlayWindow at absolute earliest point,
        # before importing heavy perception/core modules or loading configurations/models.
        from PySide6.QtWidgets import QApplication
        from gui_qt.prod.overlay_window import ProdOverlayWindow

        app = QApplication(sys.argv)
        overlay = ProdOverlayWindow(registry=None)
        overlay.show()
        overlay.add_ally_message("System", "Initializing Ally & Perception pipeline...")

        log("GUI displayed successfully, starting core pipeline initialization...", level="info")

        # Run async core initialization after GUI is visible on screen
        main_module.run_qt_app_with_overlay(app, overlay)

def main():
    # 1. Call run_header_splash() as absolute first call in run.py
    main_module = run_header_splash()
    initialize_and_run(main_module)

if __name__ == "__main__":
    main()
