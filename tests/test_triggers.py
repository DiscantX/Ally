"""Unit tests for trigger system (TurnCountTrigger, SalienceEventTrigger, ExplicitAllyTrigger, CompositeTrigger) and narrative manager integration."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from brain.memory.db import MemoryDB
from brain.memory.narrative import NarrativeMemoryManager, TextSummary
from brain.memory.triggers import (
    TurnCountTrigger,
    SalienceEventTrigger,
    ExplicitAllyTrigger,
    CompositeTrigger,
)


class TestTriggers(unittest.TestCase):
    def test_turn_count_trigger(self):
        trigger = TurnCountTrigger(interval=4)
        self.assertFalse(trigger.should_trigger({"turn": 1}))
        self.assertFalse(trigger.should_trigger({"turn": 3}))
        self.assertTrue(trigger.should_trigger({"turn": 4}))
        self.assertTrue(trigger.should_trigger({"turn": 8}))

    def test_salience_event_trigger(self):
        trigger = SalienceEventTrigger(importance_threshold=8)
        self.assertFalse(trigger.should_trigger({"importance": 5}))
        self.assertTrue(trigger.should_trigger({"importance": 8}))
        self.assertTrue(trigger.should_trigger({"importance": 10}))

    def test_explicit_ally_trigger(self):
        trigger = ExplicitAllyTrigger()
        self.assertFalse(trigger.should_trigger({"explicit_checkpoint": False}))
        self.assertFalse(trigger.should_trigger({}))
        self.assertTrue(trigger.should_trigger({"explicit_checkpoint": True}))

    def test_composite_trigger(self):
        t1 = TurnCountTrigger(interval=8)
        t2 = SalienceEventTrigger(importance_threshold=8)
        t3 = ExplicitAllyTrigger()
        composite = CompositeTrigger([t1, t2, t3])

        # None match
        self.assertFalse(composite.should_trigger({"turn": 3, "importance": 4, "explicit_checkpoint": False}))
        # Turn count matches (8)
        self.assertTrue(composite.should_trigger({"turn": 8, "importance": 2, "explicit_checkpoint": False}))
        # Importance matches (9 >= 8)
        self.assertTrue(composite.should_trigger({"turn": 3, "importance": 9, "explicit_checkpoint": False}))
        # Explicit checkpoint matches
        self.assertTrue(composite.should_trigger({"turn": 3, "importance": 2, "explicit_checkpoint": True}))


class TestNarrativeManagerTriggers(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_triggers.db")
        self.db = MemoryDB(self.db_path)
        self.provider = MagicMock()
        self.provider.generate_structured.return_value = TextSummary(summary="Medium term summary.")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_narrative_manager_high_importance_triggers_flush(self):
        manager = NarrativeMemoryManager(
            player_id="player1",
            game_id="game1",
            save_id="session_1",
            provider=self.provider,
            db=self.db,
            medium_flush_interval=8,
        )

        # Turn 1 with importance=9 should trigger medium-term flush even though turn 1 != 8
        manager.record_turn(1, "Crucial boss encounter starting.", importance=9)

        # Check if generate_structured was called (indicating medium-term flush occurred)
        self.provider.generate_structured.assert_called()
        med_entries = self.db.get_narrative_entries("player1", "game1", "session_1", "medium")
        self.assertEqual(len(med_entries), 1)

    def test_narrative_manager_explicit_checkpoint_triggers_flush(self):
        manager = NarrativeMemoryManager(
            player_id="player1",
            game_id="game1",
            save_id="session_2",
            provider=self.provider,
            db=self.db,
            medium_flush_interval=8,
        )

        # Turn 2 with explicit_checkpoint=True should trigger medium-term flush
        manager.record_turn(2, "Reached a save point.", explicit_checkpoint=True)

        self.provider.generate_structured.assert_called()
        med_entries = self.db.get_narrative_entries("player1", "game1", "session_2", "medium")
        self.assertEqual(len(med_entries), 1)


if __name__ == "__main__":
    unittest.main()
