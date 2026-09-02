"""Constants for the brain module.

This module contains all hardcoded default values, thresholds, and
magic strings used throughout the brain package. Centralizing these
values makes them easier to maintain and modify.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Default IDs
# ---------------------------------------------------------------------------

DEFAULT_PLAYER_ID: str = "default_player"
DEFAULT_GAME_ID: str = "default_game"
DEFAULT_SAVE_ID: str = "default_save"
ADHOC_IMAGE_GAME_ID: str = "adhoc_image"

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

DEFAULT_MATCH_THRESHOLD: float = 0.75
DEFAULT_LOCK_THRESHOLD: float = 0.75
DEFAULT_DEDUP_THRESHOLD: float = 0.75

# ---------------------------------------------------------------------------
# Memory defaults
# ---------------------------------------------------------------------------

DEFAULT_SHORT_TERM_CAPACITY: int = 8
DEFAULT_MEDIUM_FLUSH_INTERVAL: int = 8

# ---------------------------------------------------------------------------
# Memory tier strings
# ---------------------------------------------------------------------------

MEMORY_TIER_SHORT: str = "short"
MEMORY_TIER_MEDIUM: str = "medium"
MEMORY_TIER_LONG: str = "long"

# ---------------------------------------------------------------------------
# Personality entry types
# ---------------------------------------------------------------------------

PERSONALITY_ENTRY_MASTER: str = "master"
PERSONALITY_ENTRY_DIGEST: str = "digest"
PERSONALITY_ENTRY_MICRO: str = "micro"
