"""User configuration manager: loads user config JSON with defaults and
provides typed helpers for specific config sections.

Config file resolution order:
1. Config path passed to load_user_config(path) (optional)
2. Environment variable ALLY_CONFIG_PATH
3. state/user_config.json in project root

All other modules in this codebase import load_user_config() from here and
read their tunables directly from the returned dict, with safe defaults
defined in _DEFAULT_CONFIG below.
"""

import json
import os
import threading
from typing import Any

# ----------------------------------------------------------------------
# Default configuration
# ----------------------------------------------------------------------
_DEFAULT_CONFIG: dict[str, Any] = {
    # --- Model / reasoning -------------------------------------------------
    "ally_model": "gemini-3.5-flash-lite",
    "scribe_model": "gemini-3.5-flash-lite",
    "personality_model": "gemini-3.5-flash-lite",
    "narrative_model": "gemini-3.5-flash-lite",
    "geneology_model": "gemini-3.5-flash-lite",
    "thinking_level": "medium",
    # --- Screen / OCR pipeline ---------------------------------------------
    "match_threshold": 0.80,
    "draft_match_threshold": 0.70,
    "threshold_percent": 15,
    "pixel_diff_threshold": 25,
    "enable_cooldown": True,
    "cooldown_seconds": 2.0,
    "major_change_threshold": 50.0,
    "enable_stability_check": True,
    "stability_threshold_percent": 2.0,
    "use_ssim": True,
    "unknown_streak_threshold": 3,
    "enable_downscaling": True,
    # --- Clip classifier ---------------------------------------------------
    "clip_enabled": True,
    "clip_image_model": "Qdrant/clip-ViT-B-32-vision",
    "clip_text_model": "Qdrant/clip-ViT-B-32-text",
    "clip_skip_confidence_threshold": 0.5,
    "clip_skip_margin_threshold": 0.15,
    "clip_category_dedup_threshold": 0.75,
    # --- Speech (voice input + output) ------------------------------------
    "voice_input_enabled": False,
    "voice_output_enabled": False,
    "stt_mode": "push_to_talk",
    "stt_model_path": "model",
    "stt_sample_rate": 16000,
    "thinking_pause_seconds": 0.7,
    "tts_model": "gemini-3.1-flash-tts-preview",
    "tts_voice": "Kore",
    "tts_sample_rate": 24000,
    # --- Speech / STT config (nested under "speech" key for future growth) ---
    "speech": {
        "stt_mode": "push_to_talk",
        "stt_model_path": "model",
        "stt_sample_rate": 16000,
        "thinking_pause_seconds": 0.7,
        "tts_model": "gemini-3.1-flash-tts-preview",
        "tts_voice": "Kore",
        "tts_sample_rate": 24000,
    },
}

# ----------------------------------------------------------------------
# File-level lock for thread-safe reads
# ----------------------------------------------------------------------
_LOCK = threading.Lock()


# ----------------------------------------------------------------------
# Config loading / saving
# ----------------------------------------------------------------------
def _resolve_config_path(user_path: str | None = None, player_id: str | None = None) -> str:
    """Return the path to the user config file, using optional user_path or
    falling back to ALLY_CONFIG_PATH env var, then player profile config, then the default location."""
    if user_path:
        return user_path
    env_path = os.environ.get("ALLY_CONFIG_PATH")
    if env_path:
        return env_path
    if player_id:
        return os.path.join(os.path.dirname(__file__), "..", "data", "profiles", player_id, "user_config.json")
    return os.path.join(os.path.dirname(__file__), "..", "..", "state", "user_config.json")


def load_user_config(config_path: str | None = None, player_id: str | None = None) -> dict[str, Any]:
    """Load user config from JSON file and merge with defaults.

    Never raises -- if the file cannot be read, returns a copy of the
    default config so the rest of the pipeline can boot normally.
    """
    path = _resolve_config_path(config_path, player_id=player_id)
    with _LOCK:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    user_cfg = json.load(fh)
            else:
                user_cfg = {}
        except Exception:
            user_cfg = {}

        # Deep-merge the "speech" sub-dict
        merged = dict(_DEFAULT_CONFIG)
        for key, value in user_cfg.items():
            if key == "speech" and isinstance(value, dict):
                speech_defaults = dict(_DEFAULT_CONFIG.get("speech", {}))
                speech_defaults.update(value)
                merged["speech"] = speech_defaults
            else:
                merged[key] = value

        return merged


def save_user_config(config: dict[str, Any], config_path: str | None = None) -> None:
    """Write config dict back to the user config file.

    Creates the directory (and the file) if they don't exist.
    """
    path = _resolve_config_path(config_path)
    with _LOCK:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=4)


# ----------------------------------------------------------------------
# Typed helpers for specific config sections
# ----------------------------------------------------------------------
def get_model(key: str, config: dict[str, Any] | None = None) -> str:
    """Return the model name for a given role (e.g. "ally_model", "scribe_model")."""
    if config is None:
        config = load_user_config()
    if config.get("use_master_model", False):
        master = config.get("master_model")
        if master:
            return str(master)
    return str(config.get(key, _DEFAULT_CONFIG.get(key, "gemini-3.5-flash-lite")))


def get_thinking_level(role: str, config: dict[str, Any] | None = None) -> str:
    """Return the thinking level for a given role (e.g. "ally", "scribe")."""
    if config is None:
        config = load_user_config()
    return str(config.get("thinking_level", "medium"))
