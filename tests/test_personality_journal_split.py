import os
import tempfile
import unittest
from unittest.mock import MagicMock

from brain.memory.db import MemoryDB
from brain.memory.personality import PersonalityMemoryManager, TextSummary


class TestPersonalityJournalSplit(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_personality.db")
        self.db = MemoryDB(self.db_path)
        self.provider = MagicMock()
        self.provider.generate_structured.return_value = TextSummary(summary="Synthesized digest/micro.")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_add_journal_entry_does_not_redistill(self):
        manager = PersonalityMemoryManager(
            player_id="player1",
            provider=self.provider,
            db=self.db,
            base_personality="Scout",
        )
        manager.add_journal_entry("Gameplay journal entry.")
        self.assertIn("Gameplay journal entry.", manager._master_journal)
        self.provider.generate_structured.assert_not_called()

    def test_record_reflection_redistills(self):
        manager = PersonalityMemoryManager(
            player_id="player1",
            provider=self.provider,
            db=self.db,
            base_personality="Scout",
        )
        manager.record_reflection("Player feedback reflection.")
        self.assertIn("Player feedback reflection.", manager._master_journal)
        self.provider.generate_structured.assert_called()


if __name__ == "__main__":
    unittest.main()
