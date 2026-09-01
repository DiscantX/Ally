import unittest
from unittest.mock import MagicMock
from brain.reasoning.ally_agent import Ally
from brain.knowledge.schema.schema import AllyOutput
from cabinet.configs.config_manager import load_user_config, get_thinking_level

class TestAllyAgent(unittest.TestCase):
    def test_ally_constructor_defaults_and_custom(self):
        provider = MagicMock()
        config = load_user_config()
        ally_default = Ally(provider)
        self.assertEqual(ally_default.thinking_level, get_thinking_level("ally", config))
        self.assertIn("upbeat", ally_default.base_personality)

        ally_custom = Ally(provider, thinking_level="MEDIUM")
        self.assertEqual(ally_custom.thinking_level, "MEDIUM")

    def test_ally_decide_uses_thinking_level(self):
        provider = MagicMock()
        mock_output = AllyOutput(analysis="test", actions=[], run_boundary="none")
        provider.generate_structured.return_value = mock_output

        ally = Ally(provider, thinking_level="LOW")
        result = ally.decide("elements", "entities")

        self.assertEqual(result, mock_output)
        provider.generate_structured.assert_called_once()
        _, kwargs = provider.generate_structured.call_args
        self.assertEqual(kwargs.get("thinking_level"), "LOW")

    def test_ally_decide_perspective_context(self):
        provider = MagicMock()
        mock_output = AllyOutput(analysis="test", actions=[], run_boundary="none")
        provider.generate_structured.return_value = mock_output

        ally = Ally(provider)
        ally.decide("elements", "entities", perspective_context="Custom perspective tension notes")

        provider.generate_structured.assert_called_once()
        _, kwargs = provider.generate_structured.call_args
        contents = kwargs.get("contents")
        self.assertTrue(any("Custom perspective tension notes" in c for c in contents))

if __name__ == "__main__":
    unittest.main()
