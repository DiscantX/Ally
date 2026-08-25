# test_run_turn_skip_ally.py
import unittest
from unittest.mock import MagicMock
from PIL import Image

from collectors.base import RawObservation, ConfirmedFact
from state.sandbox import StateSandbox
from state.entity_registry import EntityRegistry
from state.genre_tracker import GenreTracker
from main import run_turn


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

        # Should not raise
        result = run_turn(obs, scribe, ally, sandbox, registry, genre_tracker, memory_manager)

        self.assertFalse(result)  # run_boundary defaults to "none"
        ally.decide.assert_not_called()  # confirms Scribe/Ally were genuinely skipped


if __name__ == "__main__":
    unittest.main()