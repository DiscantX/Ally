"""Global User Configuration Manager.
Manages loading, saving, and defaults for user-configurable settings and thresholds
stored in configs/user_config.json.
"""

import json
import os
from typing import Any
from logger.logger import log

DEFAULT_USER_CONFIG = {
    # LLM Models
    "scribe_model": "gemini-3.5-flash-lite",
    "ally_model": "gemini-3.5-flash-lite",
    "narrative_model": "gemini-3.5-flash-lite",
    "personality_model": "gemini-3.5-flash-lite",
    "geneology_model": "gemini-3.5-flash",
    "default_personality": "Scout",

    # Model Configuration
    "use_master_model": False,
    "master_model": "gemini-3.5-flash-lite",

    # Vision & Change Detection
    "threshold_percent": 5.0,
    "pixel_diff_threshold": 30,
    "major_change_threshold": 20.0,
    "enable_cooldown": False,
    "cooldown_seconds": 1.0,
    "enable_stability_check": False,
    "stability_threshold_percent": 5.0,
    "use_ssim": True,

    # Screen Classification
    "match_threshold": 0.85,
    "draft_match_threshold": 0.93,

    # Screen Bootstrapper
    "unknown_streak_threshold": 3,

    # Memory & Triggers
    "short_term_capacity": 8,
    "thinking_level": "LOW",

    # Downscaling Settings
    "enable_downscaling": True,
    "downscale_max_size": 950,
}

CONFIG_PATH = os.path.join("configs", "user_config.json")


def load_user_config() -> dict[str, Any]:
    """Load user configuration from configs/user_config.json, falling back to defaults."""
    config = DEFAULT_USER_CONFIG.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                user_data = json.load(f)
                if isinstance(user_data, dict):
                    config.update(user_data)
        except Exception as e:
            log("Error loading {}: {}", CONFIG_PATH, e)
    else:
        save_user_config(config)
    return config


def save_user_config(config: dict[str, Any]) -> None:
    """Save user configuration to configs/user_config.json."""
    os.makedirs("configs", exist_ok=True)
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        log("Error saving {}: {}", CONFIG_PATH, e)

def get_model(component_name: str, config: dict) -> str:
    """Get the correct model for a component based on master/individual settings."""
    if config.get("use_master_model", False):
        return config.get("master_model", "gemini-3.5-flash-lite")
    return config.get(component_name, "gemini-3.5-flash-lite")
