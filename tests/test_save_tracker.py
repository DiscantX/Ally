"""Unit tests for SaveTracker and save session management."""

import os
import tempfile
import time
import unittest

from brain.memory.db import MemoryDB
from brain.memory.save_tracker import SaveTracker


class TestSaveTracker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_memory.db")
        self.db = MemoryDB(self.db_path)
        self.tracker = SaveTracker(self.db)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_resolve_new_session(self):
        save_id, is_new = self.tracker.resolve_save_id("player1", "game1")
        self.assertTrue(is_new)
        self.assertTrue(save_id.startswith("session_"))

        # Verify session in DB
        session = self.db.get_latest_open_session("player1", "game1")
        self.assertIsNotNone(session)
        self.assertEqual(session["save_id"], save_id)
        self.assertEqual(session["status"], "open")

    def test_resolve_reuse_recent_session(self):
        save_id1, is_new1 = self.tracker.resolve_save_id("player1", "game1")
        self.assertTrue(is_new1)

        # Call again immediately within idle window
        save_id2, is_new2 = self.tracker.resolve_save_id("player1", "game1", idle_window_seconds=7200)
        self.assertFalse(is_new2)
        self.assertEqual(save_id1, save_id2)

    def test_resolve_stale_session_expires(self):
        save_id1, is_new1 = self.tracker.resolve_save_id("player1", "game1")
        self.assertTrue(is_new1)

        # Backdate last_active_at past idle window
        conn = self.db._connect()
        try:
            conn.execute(
                "UPDATE save_sessions SET last_active_at = datetime('now', '-1 hour') WHERE save_id = ?",
                (save_id1,)
            )
            conn.commit()
        finally:
            conn.close()

        # Resolve with idle_window_seconds=0
        save_id2, is_new2 = self.tracker.resolve_save_id("player1", "game1", idle_window_seconds=0)
        self.assertTrue(is_new2)
        self.assertNotEqual(save_id1, save_id2)

    def test_closed_session_never_reused(self):
        save_id1, is_new1 = self.tracker.resolve_save_id("player1", "game1")
        self.assertTrue(is_new1)

        # Close session
        self.tracker.close("player1", "game1", save_id1)

        # Resolve again should start a new session
        save_id2, is_new2 = self.tracker.resolve_save_id("player1", "game1")
        self.assertTrue(is_new2)
        self.assertNotEqual(save_id1, save_id2)

    def test_touch_updates_timestamp(self):
        save_id, _ = self.tracker.resolve_save_id("player1", "game1")
        session1 = self.db.get_latest_open_session("player1", "game1")
        t1 = session1["last_active_at"]

        time.sleep(0.05)
        self.tracker.touch("player1", "game1", save_id)
        session2 = self.db.get_latest_open_session("player1", "game1")
        t2 = session2["last_active_at"]

        self.assertIsNotNone(t2)


if __name__ == "__main__":
    unittest.main()
