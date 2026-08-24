"""SQLite Database Layer for Memory System.
Persists narrative memory tiers, personality journals, and entity registries.
"""

import sqlite3
import os
from typing import Any

DB_PATH = "state/memory.db"

class MemoryDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS narrative_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    save_id TEXT NOT NULL,
                    turn INTEGER NOT NULL,
                    tier TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS personality_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    aliases TEXT NOT NULL,
                    status TEXT NOT NULL,
                    facts TEXT NOT NULL,
                    first_seen INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    importance INTEGER NOT NULL,
                    UNIQUE(player_id, game_id, entity_id)
                )
            """)
            conn.commit()

    def save_narrative_entry(self, player_id: str, game_id: str, save_id: str, turn: int, tier: str, summary: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO narrative_turns (player_id, game_id, save_id, turn, tier, summary) VALUES (?, ?, ?, ?, ?, ?)",
                (player_id, game_id, save_id, turn, tier, summary)
            )
            conn.commit()

    def get_narrative_entries(self, player_id: str, game_id: str, save_id: str, tier: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM narrative_turns WHERE player_id = ? AND game_id = ? AND save_id = ? AND tier = ? ORDER BY turn ASC",
                (player_id, game_id, save_id, tier)
            )
            return [dict(row) for row in cursor.fetchall()]

    def save_personality_entry(self, player_id: str, entry_type: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO personality_journal (player_id, entry_type, content) VALUES (?, ?, ?)",
                (player_id, entry_type, content)
            )
            conn.commit()

    def get_personality_entries(self, player_id: str, entry_type: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM personality_journal WHERE player_id = ? AND entry_type = ? ORDER BY timestamp ASC",
                (player_id, entry_type)
            )
            return [dict(row) for row in cursor.fetchall()]
