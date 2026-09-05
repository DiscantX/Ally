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

from theming.palettes import resolve_module_color, THEME_LEVEL_COLORS
from theming.color_convert import hex_to_ansi_fg

# Central Registry - Module display names (colors resolved via theming package)
REGISTRY = {
    "change_detector.py": {"name": "SuperiorColliculus"},
    "inspect_coords.py": {"name": "Inspect Coords"},
    "screen_collector.py": {"name": "ScreenCollector"},
    "window_manager.py": {"name": "WindowManager"},
    "config_manager.py": {"name": "ConfigManager"},
    "scribe.py": {"name": "Scribe"},
    "ally_agent.py": {"name": "Ally"},
    "manager.py": {"name": "MemoryManager"},
    "main.py": {"name": "Main"},
    "layout.py": {"name": "Layout"},
    "gemini_provider.py": {"name": "GeminiProvider"},
    "db.py": {"name": "MemoryDB"},
    "update_docs.py": {"name": "UpdateDocs"},
    "core.py": {"name": "AllyCore"},
    "screen_classifier.py": {"name": "ScreenClassifier"},
    "screen_bootstrapper.py": {"name": "ScreenBootstrapper"},
    "layout_reader.py": {"name": "LayoutOCRReader"},
    "ocr.py": {"name": "OCR"},
    "clip_classifier.py": {"name": "ClipClassifier"},
    "screen_category_store.py": {"name": "CategoryStore"},
    "entity_registry.py": {"name": "EntityRegistry"},
    "narrative.py": {"name": "NarrativeMemory"},
    "personality.py": {"name": "PersonalityMemory"},
    "save_tracker.py": {"name": "SaveTracker"},
    "run.py": {"name": "Run"},
    "header.py": {"name": "HeaderSplash"},
    "overlay_window.py": {"name": "ProdOverlay"},
    "recognizer.py": {"name": "SpeechRecognizer"},
    "assembler.py": {"name": "UtteranceAssembler"},
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

DEFAULT_BRAIN = {"name": "General"}

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

def resolve_module_info(explicit_name: str | None = None) -> tuple[str, str, float | None]:
    """Resolves brain name, calling function/method name, and active execution timing."""
    def get_callable_name(f):
        return f.f_code.co_name

    if explicit_name:
        for k, v in REGISTRY.items():
            if v["name"].lower() == explicit_name.lower():
                return v["name"], "", None
        return explicit_name, "", None

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
                        return v["name"], callable_name, elapsed
                return mod_name, callable_name, elapsed

            file_basename = os.path.basename(filename)
            if file_basename in REGISTRY:
                entry = REGISTRY[file_basename]
                callable_name = get_callable_name(frame)
                return entry["name"], callable_name, elapsed

            frame = frame.f_back
    except Exception:
        pass

    return DEFAULT_BRAIN["name"], "", None

def log(message: str, *args, name: str | None = None, level: str = "info", **kwargs):
    """Logs a message to terminal with ANSI colors and appends plain text to log file."""
    brain_name, method_name, elapsed = resolve_module_info(name)
    
    # Terminal output is not theme-switchable yet; Slate is used as the fixed palette. See ally_decision_log.md.
    module_hex = resolve_module_color("Slate", brain_name)
    color_code = hex_to_ansi_fg(module_hex)
    reset_code = "0"
    
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
    level_lower = level.lower()
    slate_levels = THEME_LEVEL_COLORS["Slate"]
    level_hex = slate_levels.get(level_lower, slate_levels.get("info", "#d4d4d4"))
    base_level_code = hex_to_ansi_fg(level_hex)

    if level_lower == "critical":
        level_code = f"1;7;{base_level_code}"
    elif level_lower == "error":
        level_code = f"1;{base_level_code}"
    elif level_lower == "warning":
        level_code = f"1;{base_level_code}"
    else:
        level_code = base_level_code

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
