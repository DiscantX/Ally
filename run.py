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

# Check arguments to determine if we should run in quiet, headless mode
IS_HEADLESS = "--headless" in sys.argv

def main():
    if not IS_HEADLESS:
        import interfaces.visuals.header
        main_module = interfaces.visuals.header.run_header_splash()
    else:
        import main as main_module
        
    main_module.initialize_application()

if __name__ == "__main__":
    main()

