"""Validation utilities for brain module.

Centralizes common validation patterns used across multiple classes
to reduce code duplication.
"""

from __future__ import annotations

from typing import Any


def validate_non_empty_string(value: Any, name: str) -> None:
    """Validate that a value is a non-empty string.
    
    Args:
        value: The value to validate
        name: The parameter name for error messages
        
    Raises:
        ValueError: If value is not a non-empty string
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string, got: {value!r}")


def validate_not_none(value: Any, name: str) -> None:
    """Validate that a value is not None.
    
    Args:
        value: The value to validate
        name: The parameter name for error messages
        
    Raises:
        ValueError: If value is None
    """
    if value is None:
        raise ValueError(f"{name} must not be None")


def validate_player_id(player_id: str) -> None:
    """Validate player_id parameter."""
    validate_non_empty_string(player_id, "player_id")


def validate_game_id(game_id: str) -> None:
    """Validate game_id parameter."""
    validate_non_empty_string(game_id, "game_id")


def validate_save_id(save_id: str) -> None:
    """Validate save_id parameter."""
    validate_non_empty_string(save_id, "save_id")


def validate_base_personality(base_personality: str) -> None:
    """Validate base_personality parameter."""
    validate_non_empty_string(base_personality, "base_personality")


def validate_provider(provider: Any, name: str = "provider") -> None:
    """Validate provider parameter."""
    validate_not_none(provider, name)


def validate_db(db: Any, name: str = "db") -> None:
    """Validate db parameter."""
    validate_not_none(db, name)


# Convenience function for validating common triad
# Used by EntityRegistry, MemoryManager, NarrativeMemoryManager
def validate_scope_ids(player_id: str, game_id: str, save_id: str) -> None:
    """Validate the common player_id, game_id, save_id triad."""
    validate_player_id(player_id)
    validate_game_id(game_id)
    validate_save_id(save_id)
