import unittest
from unittest.mock import MagicMock
from ally.ally_agent import Ally
from schema.schema import AllyOutput

class TestAllyAgent(unittest.TestCase):
    def test_ally_constructor_defaults_and_custom(self):
        provider = MagicMock()
        ally_default = Ally(provider)
        self.assertEqual(ally_default.thinking_level, "LOW")
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

if __name__ == "__main__":
    unittest.main()
