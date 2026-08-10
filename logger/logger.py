import os
import sys
import inspect
import datetime
from pathlib import Path

# ANSI Color Codes
COLORS = {
    "cyan": "36",
    "green": "32",
    "yellow": "33",
    "magenta": "35",
    "blue": "34",
    "red": "31",
    "bright_cyan": "1;36",
    "bright_green": "1;32",
    "bright_yellow": "1;33",
    "bright_magenta": "1;35",
    "white": "37",
    "reset": "0"
}

# Central Registry mapping filename patterns / module names to Brain analogues and color codes
REGISTRY = {
    "change_detector.py": {"name": "SuperiorColliculus", "color": "cyan"},
    "inspect_coords.py": {"name": "Neow's Eye", "color": "green"},
    "screen_collector.py": {"name": "ScreenCollector", "color": "blue"},
    "window_manager.py": {"name": "WindowManager", "color": "blue"},
    "scribe.py": {"name": "Scribe", "color": "yellow"},
    "ally_agent.py": {"name": "Ally", "color": "bright_cyan"},
    "manager.py": {"name": "MemoryManager", "color": "bright_magenta"},
    "main.py": {"name": "Main", "color": "magenta"},
    "layout.py": {"name": "Layout", "color": "green"},
}

DEFAULT_BRAIN = {"name": "General", "color": "white"}

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "ally.log"

def _ensure_log_file():
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if not LOG_FILE.exists():
            LOG_FILE.touch()
    except Exception:
        pass

def _strip_ansi(text: str) -> str:
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def resolve_module_info(explicit_name: str | None = None) -> tuple[str, str]:
    """Resolves brain name and color based on explicit name, caller globals, or filename matching."""
    if explicit_name:
        for k, v in REGISTRY.items():
            if v["name"].lower() == explicit_name.lower():
                return v["name"], v["color"]
        return explicit_name, "white"

    # Inspect caller frame
    try:
        curr_frame = inspect.currentframe()
        frame = curr_frame.f_back if curr_frame else None
        while frame:
            filename = frame.f_code.co_filename
            
            if "MODULE_NAME" in frame.f_globals:
                mod_name = frame.f_globals["MODULE_NAME"]
                for k, v in REGISTRY.items():
                    if v["name"].lower() == mod_name.lower():
                        return v["name"], v["color"]
                return mod_name, "white"

            file_basename = os.path.basename(filename)
            if file_basename in REGISTRY:
                entry = REGISTRY[file_basename]
                return entry["name"], entry["color"]

            frame = frame.f_back
    except Exception:
        pass

    return DEFAULT_BRAIN["name"], DEFAULT_BRAIN["color"]

def log(message: str, *args, name: str | None = None, **kwargs):
    """
    Logs a message to terminal with ANSI colors and appends plain text to log file.
    """
    brain_name, color_key = resolve_module_info(name)
    color_code = COLORS.get(color_key, "37")
    reset_code = COLORS["reset"]

    if args or kwargs:
        try:
            formatted_message = message.format(*args, **kwargs)
        except Exception:
            formatted_message = message
    else:
        formatted_message = message

    terminal_prefix = f"\033[{color_code}m[{brain_name}]\033[{reset_code}m"
    terminal_output = f"{terminal_prefix} {formatted_message}"

    print(terminal_output)

    _ensure_log_file()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    plain_prefix = f"[{brain_name}]"
    file_line = f"{timestamp} - {plain_prefix} {formatted_message}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(file_line)
    except Exception:
        pass

class Logger:
    def __init__(self, name: str | None = None):
        self.name = name

    def info(self, message: str, *args, **kwargs):
        log(message, *args, name=self.name, **kwargs)

    def __call__(self, message: str, *args, **kwargs):
        log(message, *args, name=self.name, **kwargs)

def get_logger(name: str | None = None) -> Logger:
    return Logger(name=name)
