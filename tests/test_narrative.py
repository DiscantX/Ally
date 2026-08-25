"""Unit tests for NarrativeMemoryManager entry count and cadence handling."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from memory.db import MemoryDB
from memory.narrative import NarrativeMemoryManager, TextSummary


class TestNarrativeMemoryManagerEntryCount(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_narrative.db")
        self.db = MemoryDB(self.db_path)
        self.provider = MagicMock()
        self.provider.generate_structured.return_value = TextSummary(summary="Medium term summary.")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_same_turn_argument_increments_entry_count_and_triggers_flush(self):
        manager = NarrativeMemoryManager(
            player_id="player1",
            game_id="game1",
            save_id="session_chat",
            provider=self.provider,
            db=self.db,
            medium_flush_interval=3,
        )

        # Call record_turn 3 times with the exact same turn number (turn=1), simulating chat messages
        manager.record_turn(1, "Chat message 1")
        self.provider.generate_structured.assert_not_called()

        manager.record_turn(1, "Chat message 2")
        self.provider.generate_structured.assert_not_called()

        manager.record_turn(1, "Chat message 3")
        # Internal entry count reached 3, which matches medium_flush_interval=3. Should trigger flush!
        self.provider.generate_structured.assert_called()

        # Verify that stored entries retain turn=1 for display/logging purposes
        self.assertEqual(len(manager._short_term), 3)
        for entry in manager._short_term:
            self.assertEqual(entry.turn, 1)


if __name__ == "__main__":
    unittest.main()
