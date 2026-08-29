import unittest
from unittest.mock import MagicMock
from brain.reasoning.ally_agent import Ally
from brain.knowledge.schema.schema import AllyOutput, AllyChatOutput

class TestAllyStream(unittest.TestCase):
    def test_decide_stream(self):
        provider = MagicMock()
        mock_output = AllyOutput(analysis="streamed analysis", actions=[], run_boundary="none")
        provider.generate_structured_stream_field.return_value = mock_output

        ally = Ally(provider, thinking_level="MEDIUM")
        
        on_chunk = MagicMock()
        on_reset = MagicMock()
        
        result = ally.decide_stream(
            elements_context="elem",
            entities_context="ents",
            genre_context="RPG",
            memory_context="mem",
            personality="Scout",
            perspective_context="persp",
            on_chunk=on_chunk,
            on_reset=on_reset
        )

        self.assertEqual(result, mock_output)
        provider.generate_structured_stream_field.assert_called_once()
        _, kwargs = provider.generate_structured_stream_field.call_args
        self.assertEqual(kwargs.get("stream_field"), "analysis")
        self.assertEqual(kwargs.get("schema"), AllyOutput)
        self.assertEqual(kwargs.get("thinking_level"), "MEDIUM")
        self.assertEqual(kwargs.get("on_field_chunk"), on_chunk)
        self.assertEqual(kwargs.get("on_stream_reset"), on_reset)
        contents = kwargs.get("contents")
        self.assertTrue(any("elem" in c for c in contents))
        self.assertTrue(any("persp" in c for c in contents))

    def test_chat_stream(self):
        provider = MagicMock()
        mock_output = AllyChatOutput(response="streamed response")
        provider.generate_structured_stream_field.return_value = mock_output

        ally = Ally(provider, thinking_level="HIGH")
        
        on_chunk = MagicMock()
        on_reset = MagicMock()
        
        result = ally.chat_stream(
            elements_context="elem",
            entities_context="ents",
            genre_context="RPG",
            memory_context="mem",
            personality="Scout",
            question="Hello Ally?",
            on_chunk=on_chunk,
            on_reset=on_reset
        )

        self.assertEqual(result, mock_output)
        provider.generate_structured_stream_field.assert_called_once()
        _, kwargs = provider.generate_structured_stream_field.call_args
        self.assertEqual(kwargs.get("stream_field"), "response")
        self.assertEqual(kwargs.get("schema"), AllyChatOutput)
        # chat() / chat_stream() explicitly does NOT pass thinking_level
        self.assertNotIn("thinking_level", kwargs)
        self.assertEqual(kwargs.get("on_field_chunk"), on_chunk)
        self.assertEqual(kwargs.get("on_stream_reset"), on_reset)
        contents = kwargs.get("contents")
        self.assertTrue(any("Hello Ally?" in c for c in contents))

if __name__ == "__main__":
    unittest.main()
