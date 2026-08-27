import os
import sys
import inspect
import datetime
from pathlib import Path

# ANSI Color Codes (Expanded Palette)
COLORS = {
    # Standard Core Colors
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
    
    # High-Intensity / Bright Palette
    "bright_red": "1;91",
    "bright_green": "1;92",
    "bright_yellow": "1;93",
    "bright_blue": "1;94",
    "bright_magenta": "1;95",
    "bright_cyan": "1;96",
    "bright_white": "1;97",
    
    # Extended 256-Color Palette Options (Modern Terminal Compatible)
    "orange": "38;5;208",
    "bright_orange": "1;38;5;214",
    "salmon": "38;5;210",
    "pink": "38;5;211",
    "purple": "38;5;128",
    "lavender": "38;5;141",
    "violet": "38;5;177",
    "teal": "38;5;30",
    "mint": "38;5;121",
    "lime": "38;5;118",
    "gold": "38;5;220",
    "olive": "38;5;100",
    "sky_blue": "38;5;117",
    "steel_blue": "38;5;67",
    "dark_grey": "38;5;238",
    
    # Utility Codes
    "reset": "0",
    
    # Semantic Log Level Styles
    "lvl_debug": "38;5;244",       # Gray
    "lvl_info": "0",               # Default Terminal Text
    "lvl_warning": "1;38;5;226",   # Bright Bold Yellow
    "lvl_error": "1;31",           # Bold Red
    "lvl_critical": "1;7;31"       # Bold Red Inverted Background
}

# Central Registry - Every single file now maps to an entirely unique color
REGISTRY = {
    "change_detector.py": {"name": "SuperiorColliculus", "color": "cyan"},
    "inspect_coords.py": {"name": "Inspect Coords", "color": "green"},
    "screen_collector.py": {"name": "ScreenCollector", "color": "blue"},
    "window_manager.py": {"name": "WindowManager", "color": "steel_blue"},
    "config_manager.py": {"name": "ConfigManager", "color": "bright_blue"},
    "scribe.py": {"name": "Scribe", "color": "yellow"},
    "ally_agent.py": {"name": "Ally", "color": "bright_cyan"},
    "manager.py": {"name": "MemoryManager", "color": "bright_magenta"},
    "main.py": {"name": "Main", "color": "magenta"},
    "layout.py": {"name": "Layout", "color": "mint"},
    "gemini_provider.py": {"name": "GeminiProvider", "color": "gold"},
    "db.py": {"name": "MemoryDB", "color": "bright_green"},
    "update_docs.py": {"name": "UpdateDocs", "color": "red"},
    "init_config.py": {"name": "InitConfig", "color": "bright_orange"},
    "core.py": {"name": "AllyCore", "color": "lavender"},
    
    # --- RESERVED COLORS FOR FUTURE ADDITIONS ---
    # orange, bright_red, bright_yellow, bright_white, white, salmon, pink, purple, violet, teal, lime, olive, sky_blue
}

DEFAULT_BRAIN = {"name": "General", "color": "white"}

LOG_DIR = Path("logs")
TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"ally_{TIMESTAMP}.log"

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

def resolve_module_info(explicit_name: str | None = None) -> tuple[str, str, str]:
    """
    Resolves brain name, color, and calling function/method name.
    Returns: (brain_name, color_key, callable_name)
    """
    # FIX: Only return the pure function/method name to avoid duplication
    def get_callable_name(f):
        return f.f_code.co_name

    if explicit_name:
        for k, v in REGISTRY.items():
            if v["name"].lower() == explicit_name.lower():
                return v["name"], v["color"], ""
        return explicit_name, "white", ""

    try:
        curr_frame = inspect.currentframe()
        frame = curr_frame.f_back if curr_frame else None
        while frame:
            filename = frame.f_code.co_filename
            
            # Skip internal logger frame mechanics so we capture the true caller
            if "logger.py" in os.path.basename(filename).lower():
                frame = frame.f_back
                continue

            if "MODULE_NAME" in frame.f_globals:
                mod_name = frame.f_globals["MODULE_NAME"]
                callable_name = get_callable_name(frame)
                for k, v in REGISTRY.items():
                    if v["name"].lower() == mod_name.lower():
                        return v["name"], v["color"], callable_name
                return mod_name, "white", callable_name

            file_basename = os.path.basename(filename)
            if file_basename in REGISTRY:
                entry = REGISTRY[file_basename]
                callable_name = get_callable_name(frame)
                return entry["name"], entry["color"], callable_name

            frame = frame.f_back
    except Exception:
        pass

    return DEFAULT_BRAIN["name"], DEFAULT_BRAIN["color"], ""

def log(message: str, *args, name: str | None = None, level: str = "info", **kwargs):
    brain_name, color_key, method_name = resolve_module_info(name)
    color_code = COLORS.get(color_key, "37")
    reset_code = COLORS["reset"]
    
    dim_code = "2"
    ALIGN_WIDTH = 40  # Total character width reserved for the [Module][Method] block
    padding_spacer = f"\033[{COLORS['dark_grey']}m.\033[{COLORS['reset']}m"

    # 1. Build the Raw Strings (needed to calculate true text length without ANSI bloat)
    if method_name:
        raw_prefix = f"[{brain_name}][{method_name}]"
        # Style with Dimmed Method
        terminal_prefix = f"\033[{color_code}m[{brain_name}]\033[{color_code};{dim_code}m[{method_name}]\033[{reset_code}m"
    else:
        raw_prefix = f"[{brain_name}]"
        terminal_prefix = f"\033[{color_code}m[{brain_name}]\033[{reset_code}m"

    # 2. Calculate the Padding Needed
    # If the prefix is shorter than ALIGN_WIDTH, append the difference in spaces
    padding_spaces = f"{padding_spacer}" * max(0, ALIGN_WIDTH - len(raw_prefix))
    
    # Apply padding outside the color zones so spaces don't inherit backgrounds/decorations
    terminal_output_prefix = f"{terminal_prefix}{padding_spaces}"
    file_output_prefix = f"{raw_prefix}{padding_spaces}"

    # 3. Process the Message Body
    level_key = f"lvl_{level.lower()}"
    level_code = COLORS.get(level_key, "0")

    if args or kwargs:
        try:
            formatted_message = message.format(*args, **kwargs)
        except Exception:
            formatted_message = message
    else:
        formatted_message = message

        # 4. Construct Final Outputs (Handles multi-line messages gracefully)
    terminal_body_code = f"\033[{level_code}m"
    
    # Split the message into lines
    lines = formatted_message.split("\n")
    
    # First line gets the full prefix block
    terminal_lines = [f"{terminal_output_prefix} {terminal_body_code}{lines[0]}"]
    
    # Calculate exactly how much blank padding to add to subsequent lines
    # 1 spacer added for the gap between prefix and body
    indent_space = f"{padding_spacer}" * (ALIGN_WIDTH + 1) 
    
    for extra_line in lines[1:]:
        terminal_lines.append(f"{indent_space}{terminal_body_code}{extra_line}")
        
    # Join everything back together with newlines and close with a single reset code
    terminal_output = "\n".join(terminal_lines) + f"\033[{reset_code}m"

    print(terminal_output)

class Logger:
    def __init__(self, name: str | None = None):
        self.name = name

    def debug(self, message: str, *args, **kwargs):
        log(message, *args, name=self.name, level="debug", **kwargs)

    def info(self, message: str, *args, **kwargs):
        log(message, *args, name=self.name, level="info", **kwargs)

    def warning(self, message: str, *args, **kwargs):
        log(message, *args, name=self.name, level="warning", **kwargs)

    def error(self, message: str, *args, **kwargs):
        log(message, *args, name=self.name, level="error", **kwargs)

    def critical(self, message: str, *args, **kwargs):
        log(message, *args, name=self.name, level="critical", **kwargs)

    def __call__(self, message: str, *args, **kwargs):
        """Defaults to info level for backward compatibility when calling logger directly."""
        log(message, *args, name=self.name, level="info", **kwargs)

def get_logger(name: str | None = None) -> Logger:
    return Logger(name=name)
