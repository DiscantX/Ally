# run.py
import os
import sys
import time
import threading

# ==========================================
# CONFIGURATION OPTIONS
# ==========================================
# Minimum time (in seconds) to display the animated splash loop.
# Set to 0.0 to boot instantly as soon as main.py finishes loading.
MIN_SPLASH_DURATION = 1.0

# Target frame rate for the animated gradient cycle.
# 10 = relaxed retro shift, 24 = cinematic pacing, 60 = high-fluidity glow.
ANIMATION_FPS = 8
# ==========================================

# Check arguments to determine if we should run in quiet, headless mode
IS_HEADLESS = "--headless" in sys.argv

if not IS_HEADLESS:
    # Clear terminal immediately for a perfectly clean canvas
    os.system('cls' if os.name == 'nt' else 'clear')

# Hardcode the raw RGB strings so we don't block waiting for a logger file to compile
M_SHADES = ["38;2;255;45;220", "38;2;205;36;186", "38;2;155;27;152", "38;2;105;18;118", "38;2;55;10;85"]
C_SHADES = ["38;2;0;240;240", "38;2;1;188;202", "38;2;2;137;165", "38;2;3;86;127", "38;2;55;35;90"]
RESET = "\033[0m"
DIM = "\033[2m"

_stop_event = threading.Event()

def _animate_loop():
    """Background animation engine running independently of Python's main module loader."""
    sys.stdout.write("\033[?25l\n") # Hide text cursor
    sys.stdout.flush()
    
    # Calculate exact total delay time required per frame based on target FPS
    frame_delay = 1.0 / max(1, ANIMATION_FPS)
    
    frame = 0
    while not _stop_event.is_set():
        m0 = f"\033[{M_SHADES[(0 + frame) % 5]}m"
        m1 = f"\033[{M_SHADES[(1 + frame) % 5]}m"
        m2 = f"\033[{M_SHADES[(2 + frame) % 5]}m"
        m3 = f"\033[{M_SHADES[(3 + frame) % 5]}m"
        m4 = f"\033[{M_SHADES[(4 + frame) % 5]}m"

        c0 = f"\033[{C_SHADES[(0 + frame) % 5]}m"
        c1 = f"\033[{C_SHADES[(1 + frame) % 5]}m"
        c2 = f"\033[{C_SHADES[(2 + frame) % 5]}m"
        c3 = f"\033[{C_SHADES[(3 + frame) % 5]}m"
        c4 = f"\033[{C_SHADES[(4 + frame) % 5]}m"
        
        h_line = f" {m0}────{m1}────{m2}────{m3}────{m4}────{c4}────{c3}────{c2}────{c1}────{c0}────{RESET}"
        
        splash_frame = (
            f"{m0}    ___    __      {c0}__  __  __{RESET}\n"
            f"{m1}   /   |  / /     {c1}/ /  \\ \\/ /{RESET}\n"
            f"{m2}  / /| | / /     {c2}/ /    \\  / {RESET}\n"
            f"{m3} / ___ |/ /___  {c3}/ /___  / /  {RESET}\n"
            f"{m4}/_/  |_/_____/ {c4}/_____/ /_/   {RESET}\n"
            f"{h_line}\n"
            f"  {m0}ALLY{RESET} {DIM}• Intelligent Game Companion\n"
            f"  {c0}A{RESET}utonomous {c1}L{RESET}ive {c2}L{RESET}oop for {c3}Y{RESET}our {c4}G{RESET}ames\n"
            f"{h_line}\n"        
        )
        
        sys.stdout.write(splash_frame)
        sys.stdout.flush()
        
        # FIXED: Pure, hardware-accurate sleep delay using native thread event mechanics.
        # This blocks for exactly frame_delay, but intercepts a stop signal instantaneously.
        if _stop_event.wait(timeout=frame_delay):
            break
            
        frame += 1
        if not _stop_event.is_set():
            sys.stdout.write("\033[9F")
            sys.stdout.flush()

    sys.stdout.write("\033[?25h") # Restore text cursor
    sys.stdout.flush()

if __name__ == "__main__":
    # A. Only start background animation loop thread if we are NOT headless
    anim_thread = None
    if not IS_HEADLESS:
        anim_thread = threading.Thread(target=_animate_loop, daemon=True)
        anim_thread.start()
    
    # B. Track starting boundary time
    start_time = time.time()
    
    # C. Import main while animation runs (or silently if headless)
    import main 
    
    # D. Only enforce delay thresholds if we are NOT headless
    if not IS_HEADLESS:
        elapsed = time.time() - start_time
        if elapsed < MIN_SPLASH_DURATION:
            time.sleep(MIN_SPLASH_DURATION - elapsed)
        
        # E. Kill animation loop cleanly
        _stop_event.set()
        if anim_thread:
            anim_thread.join()
        
        # F. Clear console grid completely right before static placement
        os.system('cls' if os.name == 'nt' else 'clear')
        
        m0, m1, m2, m3, m4 = f"\033[{M_SHADES[0]}m", f"\033[{M_SHADES[1]}m", f"\033[{M_SHADES[2]}m", f"\033[{M_SHADES[3]}m", f"\033[{M_SHADES[4]}m"
        c0, c1, c2, c3, c4 = f"\033[{C_SHADES[0]}m", f"\033[{C_SHADES[1]}m", f"\033[{C_SHADES[2]}m", f"\033[{C_SHADES[3]}m", f"\033[{C_SHADES[4]}m"
        h_line = f" {m0}────{m1}────{m2}────{m3}────{m4}────{c4}────{c3}────{c2}────{c1}────{c0}────{RESET}"
        
        # G. Drop clean pixel-perfect static view at Row 0
        print(f"\n{m0}    ___    __      {c0}__  __  __{RESET}\n{m1}   /   |  / /     {c1}/ /  \\ \\/ /{RESET}\n{m2}  / /| | / /     {c2}/ /    \\  / {RESET}\n{m3} / ___ |/ /___  {c3}/ /___  / /  {RESET}\n{m4}/_/  |_/_____/ {c4}/_____/ /_/   {RESET}\n{h_line}\n  {m0}ALLY{RESET} {DIM}• Intelligent Game Companion\n  {c0}A{RESET}utonomous {c0}L{RESET}ive {c0}L{RESET}oop for {c0}Y{RESET}our {c0}G{RESET}ames\n")
    
    # H. Pass arguments straight over to main script loop
    main.initialize_application()



# {c0}ALLY{RESET} {DIM}• Intelligent Game Companion\n  {m0}A{DIM}utonomous {m1}L{DIM}ive {m2}L{DIM}oop for {c0}Y{DIM}our Games{RESET}\n")