# test_run_turn_skip_ally.py
import unittest
from unittest.mock import MagicMock
from PIL import Image

from ingestion.collectors.base import RawObservation, ConfirmedFact
from brain.state.sandbox import StateSandbox
from brain.state.entity_registry import EntityRegistry
from brain.state.genre_tracker import GenreTracker
from brain.reasoning.core import AllyCore


class TestRunTurnSkipAlly(unittest.TestCase):
    def test_skip_ally_does_not_crash(self):
        scribe = MagicMock()
        ally = MagicMock()
        sandbox = StateSandbox()
        registry = EntityRegistry()
        genre_tracker = GenreTracker()
        memory_manager = MagicMock()
        memory_manager.build_context.return_value = "ctx"
        memory_manager.get_personality_context.return_value = "personality"

        facts = [ConfirmedFact(key="hp", value="10", source="test")]
        real_image = Image.new("RGB", (64, 64), color=(0, 0, 0))
        obs = RawObservation(image=real_image, confirmed_facts=facts)
        obs.skip_ally = True

        core = AllyCore()
        core.scribe = scribe
        core.ally = ally
        core.sandbox = sandbox
        core.registry = registry
        core.genre_tracker = genre_tracker
        core.memory_manager = memory_manager

        # Should not raise
        result = core.run_turn(obs)

        self.assertFalse(result)  # run_boundary defaults to "none"
        ally.decide.assert_not_called()  # confirms Scribe/Ally were genuinely skipped


if __name__ == "__main__":
    unittest.main()
