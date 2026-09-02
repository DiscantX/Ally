"""Unit tests for PerspectiveEngine - multi-perspective analysis."""

import unittest
from unittest.mock import MagicMock, patch

from brain.reasoning.perspective_engine import PerspectiveEngine, PerspectiveScore


class TestPerspectiveEngine(unittest.TestCase):
    def setUp(self):
        # Mock provider
        self.mock_provider = MagicMock()
        self.mock_provider.generate_structured.return_value = MagicMock(
            text="Analysis from perspective"
        )
        
        # Mock config
        self.patcher = patch('brain.reasoning.perspective_engine.load_user_config')
        self.mock_config = self.patcher.start()
        self.mock_config.return_value = {
            "ally_model": "gemini-3.5-flash-lite",
            "thinking_level": "medium",
        }

    def tearDown(self):
        self.patcher.stop()

    def test_initialization(self):
        engine = PerspectiveEngine(provider=self.mock_provider)
        self.assertIsNotNone(engine)

    def test_analyze_from_perspective(self):
        engine = PerspectiveEngine(provider=self.mock_provider)
        
        result = engine.analyze_from_perspective(
            "Test situation",
            "strategic",
            "What should we do?"
        )
        
        # Should return a PerspectiveScore
        self.assertIsNotNone(result)

    def test_multi_perspective_analysis(self):
        engine = PerspectiveEngine(provider=self.mock_provider)
        
        results = engine.multi_perspective_analysis(
            "Test situation",
            ["strategic", "tactical", "emotional"],
            "What should we do?"
        )
        
        # Should return a list of results
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 3)


if __name__ == "__main__":
    unittest.main()
