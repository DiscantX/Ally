"""Unit tests for cross-session memory synthesis and close_run()."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from memory.db import MemoryDB
from memory.narrative import NarrativeMemoryManager, TextSummary
from memory.save_tracker import SaveTracker


class TestCrossSessionMemory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_cross.db")
        self.db = MemoryDB(self.db_path)
        self.save_tracker = SaveTracker(self.db)
        self.provider = MagicMock()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_close_run_writes_cross_session_memory(self):
        self.provider.generate_structured.return_value = TextSummary(summary="Synthesized cross-session summary for game.")

        save_id, _ = self.save_tracker.resolve_save_id("player1", "game1")
        manager = NarrativeMemoryManager(
            player_id="player1",
            game_id="game1",
            save_id=save_id,
            provider=self.provider,
            db=self.db,
            save_tracker=self.save_tracker,
        )

        manager.record_turn(1, "We started exploring the dungeon.")
        manager.close_run()

        cross = self.db.get_latest_cross_session("player1", "game1")
        self.assertIsNotNone(cross)
        self.assertEqual(cross["summary"], "Synthesized cross-session summary for game.")
        self.assertEqual(cross["save_id_closed"], save_id)

        session = self.db.get_latest_open_session("player1", "game1")
        self.assertIsNone(session)

    def test_build_context_surfaces_cross_session(self):
        self.db.insert_cross_session("player1", "game1", "Prior meta knowledge: watch out for traps.", "save_old")

        save_id, _ = self.save_tracker.resolve_save_id("player1", "game1")
        manager = NarrativeMemoryManager(
            player_id="player1",
            game_id="game1",
            save_id=save_id,
            provider=self.provider,
            db=self.db,
            save_tracker=self.save_tracker,
        )

        context = manager.build_context()
        self.assertIn("Cross-Session Game Summary", context)
        self.assertIn("Prior meta knowledge: watch out for traps.", context)

    def test_second_run_merges_cross_session(self):
        self.db.insert_cross_session("player1", "game1", "First run summary.", "save_1")

        self.provider.generate_structured.return_value = TextSummary(summary="Updated meta knowledge from run 1 and run 2.")

        save_id, _ = self.save_tracker.resolve_save_id("player1", "game1")
        manager = NarrativeMemoryManager(
            player_id="player1",
            game_id="game1",
            save_id=save_id,
            provider=self.provider,
            db=self.db,
            save_tracker=self.save_tracker,
        )

        manager.record_turn(1, "Starting run 2.")
        manager.close_run()

        call_args = self.provider.generate_structured.call_args
        self.assertIsNotNone(call_args)
        prompt_text = call_args[1]["contents"][0] if "contents" in call_args[1] else call_args[0][1][0]
        self.assertIn("First run summary.", prompt_text)

        cross = self.db.get_latest_cross_session("player1", "game1")
        self.assertEqual(cross["summary"], "Updated meta knowledge from run 1 and run 2.")


if __name__ == "__main__":
    unittest.main()
