"""Auto-generates a minimal per-game config.json from the currently
focused window, so a new screen-capture game can be onboarded with a
single command instead of hand-editing JSON.

Usage:
    python tools/init_config.py [game_id]

If game_id is omitted, it's derived by sanitizing the focused window's
title (e.g. "FTL - Faster Than Light" -> "ftl_faster_than_light").
Non-destructive: refuses to overwrite an existing config -- delete it
yourself first if you want a clean regeneration.

Also ensures configs/<game_id>/layouts/ exists as an empty directory.
This isn't required -- build_screen_layouts already degrades gracefully
(logged, non-fatal) when a layout dir is missing entirely -- but
creating it up front means the very first ScreenBootstrapper draft has
somewhere to land without a first-run mkdir surprise.

Windows-only (win32gui), consistent with the rest of the window-capture
stack (collectors/window_manager.py). This is the same category of
one-time manual step as MTGA's "enable detailed logs in Arena's
settings" (see docs/mtga_integration_notes.md 2.1): a prerequisite the
player does once by having the game window focused, not a per-turn
human-approval gate, so it doesn't conflict with the project's "no
manual step required for forward progress" principle.

Known limitation, not addressed here: the captured window_title must
match exactly on every future run (ScreenCollector -> ClientRect uses
win32gui.FindWindow with an exact string). A game whose title includes
a version number that changes between updates will need its config
regenerated. Worth revisiting (e.g. substring/prefix matching in
ClientRect) if this becomes a real annoyance -- not built yet since no
game has hit it in practice.
"""

import json
import os
import re
import sys

import win32gui

from infrastructure.logger import log, timed


def get_focused_window_title() -> str | None:
    """Best-effort read of the currently focused window's title."""
    handle = win32gui.GetForegroundWindow()
    if not handle:
        return None
    title = win32gui.GetWindowText(handle)
    return title or None


def sanitize_game_id(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_") or "unknown_game"


def build_config(game_id: str, window_title: str) -> dict:
    return {
        "game_id": game_id,
        "window_title": window_title,
        "layout_dir": f"configs/{game_id}/layouts",
        "source_tag": f"ocr:{game_id}",
    }


@timed
def init_config(game_id: str | None = None, window_title: str | None = None) -> str:
    """Creates configs/<game_id>/config.json. Returns the path (whether
    freshly written, or an already-existing config left untouched).

    window_title, if not supplied, is read from the currently focused
    window -- so the expected flow is: alt-tab into the game, then run
    this (or let main.py call it automatically when no config exists
    yet for the requested game_id)."""
    config_dir_hint = game_id
    config_path_hint = (
        os.path.join("configs", config_dir_hint, "config.json") if config_dir_hint else None
    )

    # If we already know where we'd look and it exists, skip touching
    # the focused window at all -- no need to require the game be
    # focused on a run that isn't actually creating anything.
    if config_path_hint and os.path.exists(config_path_hint):
        log(f"Config already exists at {config_path_hint} -- leaving it untouched.")
        return config_path_hint

    if window_title is None:
        window_title = get_focused_window_title()
        if not window_title:
            raise RuntimeError(
                "Could not read the focused window title. Make sure the "
                "target game window is focused, or pass window_title "
                "explicitly."
            )

    if game_id is None:
        game_id = sanitize_game_id(window_title)

    config_dir = os.path.join("configs", game_id)
    config_path = os.path.join(config_dir, "config.json")
    layout_dir = os.path.join(config_dir, "layouts")

    if os.path.exists(config_path):
        log(f"Config already exists at {config_path} -- leaving it untouched.")
        return config_path

    os.makedirs(layout_dir, exist_ok=True)
    config = build_config(game_id, window_title)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)

    log(f"Wrote new config for '{game_id}' (window: '{window_title}') to {config_path}")
    return config_path


if __name__ == "__main__":
    arg_game_id = sys.argv[1] if len(sys.argv) > 1 else None
    path = init_config(game_id=arg_game_id)
    log("Config ready at: {path}", path=path)