"""Unit tests for Scribe - LLM-based screen description."""

import unittest
from unittest.mock import MagicMock, patch

from brain.perception.scribe import Scribe


class TestScribe(unittest.TestCase):
    def setUp(self):
        # Mock the provider
        self.mock_provider = MagicMock()
        self.mock_provider.generate_structured.return_value = MagicMock(
            text="A combat screen with health bars and enemy units"
        )
        
        # Mock config
        self.patcher = patch('brain.perception.scribe.load_user_config')
        self.mock_config = self.patcher.start()
        self.mock_config.return_value = {
            "thinking_level": "medium",
        }

    def tearDown(self):
        self.patcher.stop()

    def test_initialization(self):
        scribe = Scribe(provider=self.mock_provider)
        self.assertIsNotNone(scribe)
        self.assertEqual(scribe.provider, self.mock_provider)

    def test_describe_screen_with_image(self):
        scribe = Scribe(provider=self.mock_provider)
        
        # Mock image
        mock_image = MagicMock()
        
        result = scribe.describe_screen(mock_image)
        
        # Verify the provider was called
        self.mock_provider.generate_structured.assert_called_once()

    @patch('brain.perception.scribe.log')
    def test_describe_screen_without_provider(self, mock_log):
        scribe = Scribe(provider=None)
        
        mock_image = MagicMock()
        result = scribe.describe_screen(mock_image)
        
        # Should return empty result when no provider
        self.assertIsNotNone(result)
        mock_log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
