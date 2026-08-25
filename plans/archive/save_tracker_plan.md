# Sub-Plan: Pass 1 Step 1 — `SaveTracker` (`save_id` Resolution and Tracking)

## Overview

This sub-plan specifies the implementation details for **Pass 1 Step 1** of the Ally memory correctness pass. It replaces the naive `uuid.uuid4()` generation in `main.py` with persistent `save_sessions` tracking in SQLite, allowing Ally to resume run memory if restarted mid-run within an idle window, while starting clean sessions after run closures or stale idle periods.

---

## 1. DB Table Schema Additions (`memory/db.py`)

Add the `save_sessions` table to `MemoryDB._init_db()` in [`memory/db.py`](memory/db.py):

```sql
CREATE TABLE IF NOT EXISTS save_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT NOT NULL,
    game_id TEXT NOT NULL,
    save_id TEXT NOT NULL,
    status TEXT NOT NULL,          -- "open" or "closed"
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, game_id, save_id)
)
```

### New `MemoryDB` Methods

- `get_latest_open_session(player_id: str, game_id: str) -> dict[str, Any] | None`:
  Queries the most recent open session for `(player_id, game_id)` where `status = 'open'`, ordered by `last_active_at DESC` (limit 1).
- `create_save_session(player_id: str, game_id: str, save_id: str) -> None`:
  Inserts a new row with `status = 'open'`, `started_at = CURRENT_TIMESTAMP`, and `last_active_at = CURRENT_TIMESTAMP`.
- `touch_save_session(player_id: str, game_id: str, save_id: str) -> None`:
  Updates `last_active_at = CURRENT_TIMESTAMP` for the specified active session.
- `close_save_session(player_id: str, game_id: str, save_id: str) -> None`:
  Updates `status = 'closed'` for the specified session.

---

## 2. API and Implementation Details (`memory/save_tracker.py`)

Create a new module [`memory/save_tracker.py`](memory/save_tracker.py) adhering to the "keep it dumb" pattern (similar to `StateSandbox`):

```python
"""SaveTracker: Resolves and tracks active run save_sessions in SQLite.
Keeps save_id persistence state clean and separate from narrative distillation.
"""

from datetime import datetime, timezone
import uuid
from typing import Any
from memory.db import MemoryDB

class SaveTracker:
    def __init__(self, db: MemoryDB):
        self.db = db

    def resolve_save_id(
        self, player_id: str, game_id: str, idle_window_seconds: int = 7200
    ) -> tuple[str, bool]:
        """Resolves whether to resume the latest open session or start a new one.
        
        Returns:
            Tuple of (save_id, is_new_session).
        """
        latest = self.db.get_latest_open_session(player_id, game_id)
        if latest:
            last_active = latest["last_active_at"]
            # Parse timestamp (handle SQLite string format if necessary)
            active_dt = self._parse_dt(last_active)
            now_dt = datetime.now(timezone.utc)
            
            # Calculate elapsed seconds
            if active_dt:
                elapsed = (now_dt - active_dt).total_seconds()
                if 0 <= elapsed <= idle_window_seconds:
                    # Reuse save_id and touch
                    save_id = latest["save_id"]
                    self.touch(player_id, game_id, save_id)
                    return save_id, False

        # Otherwise, generate new save_id and create open session
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
            # SQLite default CURRENT_TIMESTAMP format: YYYY-MM-DD HH:MM:SS
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                return datetime.fromisoformat(dt_str).astimezone(timezone.utc)
            except Exception:
                return None
```

---

## 3. Wiring into `main.py` and `MemoryManager`

1. **Initialize `SaveTracker`**:
   Instantiate `MemoryDB` and `SaveTracker` in `main.py`'s `execute_run()`.
2. **Replace `uuid.uuid4()`**:
   Instead of `save_id=f"session_{uuid.uuid4().hex[:8]}"`, call:

   ```python
   save_id, is_new = save_tracker.resolve_save_id(player_id="default_player", game_id=game_id)
   ```

3. **Wire `touch` activity**:
   Pass `save_tracker` (or inject it) into `MemoryManager` / `NarrativeMemoryManager`. In `NarrativeMemoryManager.record_turn()` (which is called on every turn and every chat message), invoke `self.save_tracker.touch(self.player_id, self.game_id, self.save_id)`.

---

## 4. Unit Tests Design (`memory/test_save_tracker.py`)

Create [`memory/test_save_tracker.py`](memory/test_save_tracker.py) using `unittest` and a temporary SQLite database (or `:memory:`):

- **`test_resolve_new_session`**:
  Calling `resolve_save_id` for a fresh `(player_id, game_id)` creates a new open session and returns `is_new=True`.
- **`test_resolve_reuse_recent_session`**:
  Calling `resolve_save_id` shortly after creating an open session reuses the same `save_id` and returns `is_new=False`.
- **`test_resolve_stale_session_expires`**:
  If the last active timestamp is older than `idle_window_seconds` (mocked or tested with `idle_window_seconds=0` / manual DB backdating), `resolve_save_id` closes or ignores the stale session and creates a new one (`is_new=True`).
- **`test_closed_session_never_reused`**:
  If a session is explicitly closed via `save_tracker.close()`, a subsequent call to `resolve_save_id` ignores it and generates a brand-new `save_id` (`is_new=True`).
- **`test_touch_updates_timestamp`**:
  Calling `touch` updates `last_active_at` in the database.
