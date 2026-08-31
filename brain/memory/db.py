"""SQLite Database Layer for Memory System.
Persists narrative memory tiers, personality journals, and entity registries.
"""

import sqlite3
import os
from typing import Any
from infrastructure.logger import log, pretty_format, timed

DB_PATH = os.path.join("data", "profiles", "default_player", "memory.db")

class MemoryDB:
    def __init__(self, db_path: str | None = None, player_id: str = "default_player"):
        self.player_id = player_id
        self.db_path = db_path or os.path.join("data", "profiles", player_id, "memory.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @timed
    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS save_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    save_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_active_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(player_id, game_id, save_id)
                )
            """)
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
                    save_id TEXT NOT NULL DEFAULT 'default_save',
                    entity_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    aliases TEXT NOT NULL,
                    status TEXT NOT NULL,
                    facts TEXT NOT NULL,
                    first_seen INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    importance INTEGER NOT NULL,
                    external_id TEXT,
                    UNIQUE(player_id, game_id, save_id, entity_id)
                )
            """)
            try:
                conn.execute("ALTER TABLE entities ADD COLUMN save_id TEXT NOT NULL DEFAULT 'default_save'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE entities ADD COLUMN external_id TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_scope_id ON entities(player_id, game_id, save_id, entity_id)")
            except sqlite3.OperationalError:
                pass
            
            cursor = conn.execute("PRAGMA index_list(entities)")
            indexes_info = []
            for row in cursor.fetchall():
                idx_name = row["name"]
                info_cursor = conn.execute(f"PRAGMA index_info({idx_name})")
                columns = [info_row["name"] for info_row in info_cursor.fetchall()]
                indexes_info.append({
                    "table": "entities",
                    "name": idx_name,
                    "unique": bool(row["unique"]),
                    "origin": row["origin"],
                    "columns": columns
                })
            log("Entities indexes:\n{indexes}", indexes=pretty_format(indexes_info, remove_brackets=True))

            conn.execute("""
                CREATE TABLE IF NOT EXISTS cross_session_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    save_id_closed TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS screen_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT,
                    kind TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    source TEXT NOT NULL DEFAULT 'learned',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                conn.execute("ALTER TABLE screen_categories ADD COLUMN source TEXT NOT NULL DEFAULT 'learned'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE screen_categories ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
            except sqlite3.OperationalError:
                pass
            conn.commit()
        finally:
            conn.close()

    def get_latest_open_session(self, player_id: str, game_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM save_sessions WHERE player_id = ? AND game_id = ? AND status = 'open' ORDER BY last_active_at DESC LIMIT 1",
                (player_id, game_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_save_session(self, player_id: str, game_id: str, save_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO save_sessions (player_id, game_id, save_id, status) VALUES (?, ?, ?, 'open')",
                (player_id, game_id, save_id)
            )
            conn.commit()
        finally:
            conn.close()

    def touch_save_session(self, player_id: str, game_id: str, save_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE save_sessions SET last_active_at = CURRENT_TIMESTAMP WHERE player_id = ? AND game_id = ? AND save_id = ? AND status = 'open'",
                (player_id, game_id, save_id)
            )
            conn.commit()
        finally:
            conn.close()

    def close_save_session(self, player_id: str, game_id: str, save_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE save_sessions SET status = 'closed' WHERE player_id = ? AND game_id = ? AND save_id = ?",
                (player_id, game_id, save_id)
            )
            conn.commit()
        finally:
            conn.close()

    def save_narrative_entry(self, player_id: str, game_id: str, save_id: str, turn: int, tier: str, summary: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO narrative_turns (player_id, game_id, save_id, turn, tier, summary) VALUES (?, ?, ?, ?, ?, ?)",
                (player_id, game_id, save_id, turn, tier, summary)
            )
            conn.commit()
        finally:
            conn.close()

    def get_narrative_entries(self, player_id: str, game_id: str, save_id: str, tier: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM narrative_turns WHERE player_id = ? AND game_id = ? AND save_id = ? AND tier = ? ORDER BY turn ASC",
                (player_id, game_id, save_id, tier)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def save_personality_entry(self, player_id: str, entry_type: str, content: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO personality_journal (player_id, entry_type, content) VALUES (?, ?, ?)",
                (player_id, entry_type, content)
            )
            conn.commit()
        finally:
            conn.close()

    def get_personality_entries(self, player_id: str, entry_type: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM personality_journal WHERE player_id = ? AND entry_type = ? ORDER BY timestamp ASC",
                (player_id, entry_type)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_latest_cross_session(self, player_id: str, game_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM cross_session_memory WHERE player_id = ? AND game_id = ? ORDER BY timestamp DESC, id DESC LIMIT 1",
                (player_id, game_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def insert_cross_session(self, player_id: str, game_id: str, summary: str, save_id_closed: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO cross_session_memory (player_id, game_id, summary, save_id_closed) VALUES (?, ?, ?, ?)",
                (player_id, game_id, summary, save_id_closed)
            )
            conn.commit()
        finally:
            conn.close()

    def load_entities(self, player_id: str, game_id: str, save_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM entities WHERE player_id = ? AND game_id = ? AND save_id = ?",
                (player_id, game_id, save_id)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    @timed
    def upsert_entities(self, player_id: str, game_id: str, save_id: str, entities: list[dict[str, Any]]) -> None:
        conn = self._connect()
        try:
            log("upsert_entities: player_id={player_id}, game_id={game_id}, save_id={save_id}, count={count}", player_id=player_id, game_id=game_id, save_id=save_id, count=len(entities))
            for ent in entities:
                log("Upserting entity: id={entity_id}, name={canonical_name}", entity_id=ent.get('entity_id'), canonical_name=ent.get('canonical_name'))
                conn.execute("""
                    INSERT INTO entities (
                        player_id, game_id, save_id, entity_id, entity_type, canonical_name,
                        aliases, status, facts, first_seen, last_seen, importance, external_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(player_id, game_id, save_id, entity_id) DO UPDATE SET
                        entity_type = excluded.entity_type,
                        canonical_name = excluded.canonical_name,
                        aliases = excluded.aliases,
                        status = excluded.status,
                        facts = excluded.facts,
                        last_seen = excluded.last_seen,
                        importance = excluded.importance,
                        external_id = excluded.external_id
                """, (
                    player_id,
                    game_id,
                    save_id,
                    ent.get("entity_id"),
                    ent.get("entity_type", "unknown"),
                    ent.get("canonical_name"),
                    ent.get("aliases", "[]"),
                    ent.get("status", "active"),
                    ent.get("facts", "[]"),
                    ent.get("first_seen", 0),
                    ent.get("last_seen", 0),
                    ent.get("importance", 0),
                    ent.get("external_id"),
                ))
            conn.commit()
        finally:
            conn.close()

    def get_screen_categories(self, game_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM screen_categories WHERE game_id IS NULL OR game_id = ?",
                (game_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def insert_screen_category(
        self, game_id: str | None, kind: str, text: str, embedding: bytes, source: str = "learned"
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO screen_categories (game_id, kind, text, embedding, source) VALUES (?, ?, ?, ?, ?)",
                (game_id, kind, text, embedding, source)
            )
            conn.commit()
        finally:
            conn.close()

    def count_screen_categories(self, source: str | None = None) -> int:
        conn = self._connect()
        try:
            if source:
                cursor = conn.execute("SELECT COUNT(*) as c FROM screen_categories WHERE source = ?", (source,))
            else:
                cursor = conn.execute("SELECT COUNT(*) as c FROM screen_categories")
            row = cursor.fetchone()
            return row["c"] if row else 0
        except sqlite3.OperationalError:
            return 0
        finally:
            conn.close()
