"""Unit tests for Ally - the main AI agent."""

import unittest
from unittest.mock import MagicMock, patch

from brain.reasoning.ally_agent import Ally


class TestAllyAgent(unittest.TestCase):
    def setUp(self):
        # Mock dependencies
        self.mock_provider = MagicMock()
        self.mock_provider.generate_structured.return_value = MagicMock(
            text="Thinking..."
        )
        
        # Mock config
        self.patcher = patch('brain.reasoning.ally_agent.load_user_config')
        self.mock_config = self.patcher.start()
        self.mock_config.return_value = {
            "ally_model": "gemini-3.5-flash-lite",
            "thinking_level": "medium",
            "default_personality": "Scout",
        }

    def tearDown(self):
        self.patcher.stop()

    def test_initialization(self):
        ally = Ally(
            provider=self.mock_provider,
            base_personality="Scout",
        )
        self.assertIsNotNone(ally)
        self.assertEqual(ally.base_personality, "Scout")

    def test_respond_to_player(self):
        ally = Ally(
            provider=self.mock_provider,
            base_personality="Scout",
        )
        
        result = ally.respond_to_player("Hello", context="Test context")
        
        # Should return a response
        self.assertIsNotNone(result)

    def test_respond_to_game_event(self):
        ally = Ally(
            provider=self.mock_provider,
            base_personality="Scout",
        )
        
        result = ally.respond_to_game_event("Enemy appeared", context="Test context")
        
        # Should return a response
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
