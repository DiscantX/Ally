"""SaveTracker: Resolves and tracks active run save_sessions in SQLite.
Keeps save_id persistence state clean and separate from narrative distillation.
"""

from datetime import datetime, timezone
import uuid
from typing import Any
from brain.memory.db import MemoryDB

from infrastructure.logger import log, timed

class SaveTracker:
    def __init__(self, db: MemoryDB):
        if db is None:
            raise ValueError("SaveTracker requires a non-None MemoryDB instance")
        log("Initializing SaveTracker...")
        self.db = db

    def resolve_save_id(
        self, player_id: str, game_id: str, idle_window_seconds: int = 7200
    ) -> tuple[str, bool]:
        """Resolves whether to resume the latest open session or start a new one.
        
        Returns:
            Tuple of (save_id, is_new_session).
        """
        log("Resolving save_id for player={player_id}, game={game_id}...", player_id=player_id, game_id=game_id)
        latest = self.db.get_latest_open_session(player_id, game_id)
        if latest:
            last_active = latest["last_active_at"]
            active_dt = self._parse_dt(last_active)
            now_dt = datetime.now(timezone.utc)
            
            if active_dt:
                elapsed = (now_dt - active_dt).total_seconds()
                if 0 <= elapsed <= idle_window_seconds:
                    save_id = latest["save_id"]
                    self.touch(player_id, game_id, save_id)
                    return save_id, False

        save_id = f"session_{uuid.uuid4().hex[:8]}"
        self.db.create_save_session(player_id, game_id, save_id)
        return save_id, True

    def touch(self, player_id: str, game_id: str, save_id: str) -> None:
        """Updates last_active_at timestamp for the current session."""
        self.db.touch_save_session(player_id, game_id, save_id)

    def close(self, player_id: str, game_id: str, save_id: str) -> None:
        """Marks the session status as closed."""
        self.db.close_save_session(player_id, game_id, save_id)

    def _parse_dt(self, dt_str: str | None) -> datetime | None:
        if not dt_str:
            return None
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                return datetime.fromisoformat(dt_str).astimezone(timezone.utc)
            except Exception as e:
                log("Failed to parse datetime '{dt_str}': {error}", dt_str=dt_str, error=str(e), level="warning")
                return None
