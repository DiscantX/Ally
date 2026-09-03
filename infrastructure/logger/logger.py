import os
import sys
import inspect
import datetime
import pprint
import re
import threading
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Any

# ANSI Color Codes (Expanded Palette)
COLORS = {
    # Standard Core Colors
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
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
    
    # Vertical & Horizontal Smooth Gradient Palette
    "magenta": "38;2;255;45;220",    # Step 0: Vibrant Hot Pink / Magenta
    "magenta_1": "38;2;205;36;186",  # Step 1: Rich Fuchsia
    "magenta_2": "38;2;155;27;152",  # Step 2: Deep Violet
    "magenta_3": "38;2;105;18;118",  # Step 3: Dark Purple
    "magenta_4": "38;2;55;10;85",    # Step 4: Midnight Indigo

    "cyan": "38;2;0;240;240",       # Step 0: Electric Neon Cyan
    "cyan_1": "38;2;1;188;202",     # Step 1: Sky Teal
    "cyan_2": "38;2;2;137;165",     # Step 2: Slate Ocean Blue
    "cyan_3": "38;2;3;86;127",      # Step 3: Deep Marine Blue
    "cyan_4": "38;2;5;35;90",       # Step 4: Cyber Midnight Blue
    
    # Utility Codes
    "reset": "0",
    
    # Semantic Log Level Styles
    "lvl_debug": "38;5;240",       # Clean Charcoal Gray
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
    "core.py": {"name": "AllyCore", "color": "lavender"},
    "screen_classifier.py": {"name": "ScreenClassifier", "color": "mint"},
    "screen_bootstrapper.py": {"name": "ScreenBootstrapper", "color": "salmon"},
    "layout_reader.py": {"name": "LayoutOCRReader", "color": "teal"},
    "ocr.py": {"name": "OCR", "color": "olive"},
    "clip_classifier.py": {"name": "ClipClassifier", "color": "violet"},
    "screen_category_store.py": {"name": "CategoryStore", "color": "lavender"},
    "entity_registry.py": {"name": "EntityRegistry", "color": "sky_blue"},
    "narrative.py": {"name": "NarrativeMemory", "color": "pink"},
    "personality.py": {"name": "PersonalityMemory", "color": "purple"},
    "save_tracker.py": {"name": "SaveTracker", "color": "dark_grey"},
    "run.py": {"name": "Run", "color": "bright_cyan"},
    "header.py": {"name": "HeaderSplash", "color": "orange"},
    "overlay_window.py": {"name": "ProdOverlay", "color": "cyan"},
    "recognizer.py": {"name": "SpeechRecognizer", "color": "cyan_1"},
    "assembler.py": {"name": "UtteranceAssembler", "color": "magenta_1"},
}

@dataclass
class LogEntry:
    brain_name: str
    method_name: str
    message: str
    level: str
    timestamp: datetime.datetime

_subscribers: list[Callable[[LogEntry], None]] = []

def subscribe(callback: Callable[[LogEntry], None]) -> None:
    if callback not in _subscribers:
        _subscribers.append(callback)

def unsubscribe(callback: Callable[[LogEntry], None]) -> None:
    if callback in _subscribers:
        _subscribers.remove(callback)

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
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

# Thread-safe storage for function timing stacks
_timing_storage = threading.local()

def _get_timing_stack() -> dict:
    if not hasattr(_timing_storage, 'stack'):
        _timing_storage.stack = {}
    return _timing_storage.stack

def timed(func: Callable) -> Callable:
    """Decorator to track function execution time seamlessly with the tree logger."""
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        stack = _get_timing_stack()
        code_obj = func.__code__
        if code_obj not in stack:
            stack[code_obj] = []
        stack[code_obj].append(time.perf_counter())
        try:
            return func(*args, **kwargs)
        finally:
            if code_obj in stack and stack[code_obj]:
                stack[code_obj].pop()
                if not stack[code_obj]:
                    del stack[code_obj]
    return wrapper

timer = timed

def resolve_module_info(explicit_name: str | None = None) -> tuple[str, str, str, float | None]:
    """Resolves brain name, color, calling function/method name, and active execution timing."""
    def get_callable_name(f):
        return f.f_code.co_name

    if explicit_name:
        for k, v in REGISTRY.items():
            if v["name"].lower() == explicit_name.lower():
                return v["name"], v["color"], "", None
        return explicit_name, "white", "", None

    try:
        curr_frame = inspect.currentframe()
        frame = curr_frame.f_back if curr_frame else None
        stack_timings = _get_timing_stack()

        while frame:
            filename = frame.f_code.co_filename
            
            if "logger.py" in os.path.basename(filename).lower():
                frame = frame.f_back
                continue

            elapsed = None
            if frame.f_code in stack_timings and stack_timings[frame.f_code]:
                elapsed = time.perf_counter() - stack_timings[frame.f_code][-1]

            if "MODULE_NAME" in frame.f_globals:
                mod_name = frame.f_globals["MODULE_NAME"]
                callable_name = get_callable_name(frame)
                for k, v in REGISTRY.items():
                    if v["name"].lower() == mod_name.lower():
                        return v["name"], v["color"], callable_name, elapsed
                return mod_name, "white", callable_name, elapsed

            file_basename = os.path.basename(filename)
            if file_basename in REGISTRY:
                entry = REGISTRY[file_basename]
                callable_name = get_callable_name(frame)
                return entry["name"], entry["color"], callable_name, elapsed

            frame = frame.f_back
    except Exception:
        pass

    return DEFAULT_BRAIN["name"], DEFAULT_BRAIN["color"], "", None

def log(message: str, *args, name: str | None = None, level: str = "info", **kwargs):
    """Logs a message to terminal with ANSI colors and appends plain text to log file."""
    # FIX: Intercept logic completely dropped because run.py completely handles
    # thread cleanup and clearing before handing control to the main core.

    brain_name, color_key, method_name, elapsed = resolve_module_info(name)
    color_code = COLORS.get(color_key, "37")
    reset_code = COLORS["reset"]
    
    dim_code = "2"
    ALIGN_WIDTH = 32  # Total character width reserved for the [Module][Method] block

    time_str = f"[{elapsed:.5f}s]" if elapsed is not None else ""

    # 1. Build the Raw Strings
    if method_name:
        raw_prefix = f"[{brain_name}][{method_name}]{time_str}"
        terminal_prefix = f"\033[{color_code}m[{brain_name}]\033[{color_code};{dim_code}m[{method_name}]\033[0;{dim_code}m{time_str}\033[{reset_code}m"
    else:
        if elapsed is not None:
            raw_prefix = f"[{brain_name}]{time_str}"
            terminal_prefix = f"\033[{color_code}m[{brain_name}]\033[0;{dim_code}m{time_str}\033[{reset_code}m"
        else:
            raw_prefix = f"[{brain_name}]"
            terminal_prefix = f"\033[{color_code}m[{brain_name}]\033[{reset_code}m"

    # 2. Calculate the Padding Needed
    padding_spaces = " " * max(0, ALIGN_WIDTH - len(raw_prefix))
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

    # 4. Construct Final Outputs with Multi-line Indentation support
    terminal_body_code = f"\033[{level_code}m"
    lines = formatted_message.split("\n")
    
    # First line maps the padded tag prefix
    terminal_lines = [f"{terminal_output_prefix} {terminal_body_code}{lines[0]}"]
    
    # Subsequent line padding alignment calculator
    indent_space = " " * (ALIGN_WIDTH + 1) 
    for extra_line in lines[1:]:
        terminal_lines.append(f"{indent_space}{terminal_body_code}{extra_line}")
        
    terminal_output = "\n".join(terminal_lines) + f"\033[{reset_code}m"

    print(terminal_output)

    # 5. File System Logging Persistence
    _ensure_log_file()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    file_line = f"{timestamp} - {level.upper()} - {file_output_prefix} {formatted_message}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(file_line)
    except Exception:
        pass

    # 6. Subscriber Pub/Sub Dispatch
    try:
        entry = LogEntry(
            brain_name=brain_name,
            method_name=method_name,
            message=formatted_message,
            level=level,
            timestamp=datetime.datetime.now()
        )
        for sub in list(_subscribers):
            try:
                sub(entry)
            except Exception:
                pass
    except Exception:
        pass

# FIX: Re-added full Logger class definition structures that were clipped!
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
        log(message, *args, name=self.name, level="info", **kwargs)

def get_logger(name: str | None = None) -> Logger:
    return Logger(name=name)

def pretty_format(obj: Any, remove_brackets: bool = False) -> str:
    """Pretty formats complex objects (lists, dicts) for logs, with optional bracket stripping."""
    formatted = pprint.pformat(obj, width=100, compact=True)
    if remove_brackets:
        formatted = formatted.strip()
        if formatted.startswith('[') and formatted.endswith(']'):
            formatted = formatted[1:-1].strip()
        elif formatted.startswith('{') and formatted.endswith('}'):
            formatted = formatted[1:-1].strip()
    return formatted

