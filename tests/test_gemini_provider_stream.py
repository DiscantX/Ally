import unittest
from unittest.mock import MagicMock
from pydantic import BaseModel
from PIL import Image
from google.genai import types
from google.genai._gaos.types.interactions.textcontent import TextContent
from google.genai._gaos.types.interactions.imagecontent import ImageContent
from infrastructure.llm.providers.gemini_provider import GeminiProvider

class SampleSchema(BaseModel):
    answer: str

class TestGeminiProviderStream(unittest.TestCase):
    def test_generate_structured_stream_with_nested_thought_content(self):
        mock_client = MagicMock()
        
        # Mock interactions events with nested thought content (delta.content.text)
        event1 = MagicMock()
        event1.delta.type = "thought_summary"
        event1.delta.content = MagicMock()
        event1.delta.content.type = "text"
        event1.delta.content.text = "Thinking process step 1..."
        
        event2 = MagicMock()
        event2.delta.type = "thought_summary"
        event2.delta.content = "Thinking process step 2..." # also test flat string fallback
        
        event3 = MagicMock()
        event3.delta.type = "text"
        event3.delta.text = '{"answer": "success"}'
        
        mock_client.interactions.create.return_value = [event1, event2, event3]
        
        provider = GeminiProvider(client=mock_client)
        
        thought_chunks = []
        def on_thought(text: str):
            thought_chunks.append(text)
            
        result = provider.generate_structured_stream(
            model="gemini-2.5-flash",
            contents=["test prompt"],
            schema=SampleSchema,
            on_thought_chunk=on_thought
        )
        
        self.assertEqual(result.answer, "success")
        self.assertEqual(thought_chunks, ["Thinking process step 1...", "Thinking process step 2..."])
        mock_client.interactions.create.assert_called_once()

    def test_generate_structured_stream_no_json(self):
        mock_client = MagicMock()
        event = MagicMock()
        event.delta = None
        mock_client.interactions.create.return_value = [event]
        
        provider = GeminiProvider(client=mock_client)
        with self.assertRaises(ValueError):
            provider.generate_structured_stream(
                model="gemini-2.5-flash",
                contents=["test prompt"],
                schema=SampleSchema
            )

    def test_build_interactions_input_text_only(self):
        provider = GeminiProvider()
        res = provider._to_provider_input(["a plain prompt"])
        self.assertEqual(len(res), 1)
        self.assertIsInstance(res[0], TextContent)
        self.assertEqual(res[0].text, "a plain prompt")
        self.assertEqual(res[0].type, "text")

    def test_build_interactions_input_multimodal(self):
        provider = GeminiProvider()
        img = Image.new("RGB", (10, 10), color="red")
        res = provider._to_provider_input([img, "a prompt"])
        self.assertEqual(len(res), 2)
        self.assertIsInstance(res[0], ImageContent)
        self.assertEqual(res[0].type, "image")
        self.assertTrue(res[0].data)
        self.assertEqual(res[0].mime_type, "image/png")
        self.assertIsInstance(res[1], TextContent)
        self.assertEqual(res[1].text, "a prompt")
        self.assertEqual(res[1].type, "text")

    def test_build_interactions_input_unsupported_type(self):
        provider = GeminiProvider()
        with self.assertRaises(TypeError):
            provider._to_provider_input([12345])

    def test_multimodal_input_formatting(self):
        mock_client = MagicMock()
        response = MagicMock()
        response.output_text = '{"answer": "multimodal success"}'
        mock_client.interactions.create.return_value = response

        provider = GeminiProvider(client=mock_client)
        img = Image.new("RGB", (10, 10), color="blue")

        result = provider.generate_structured(
            model="gemini-2.5-flash",
            contents=[img, "Describe this image"],
            schema=SampleSchema
        )

        self.assertEqual(result.answer, "multimodal success")
        mock_client.interactions.create.assert_called_once()
        _, kwargs = mock_client.interactions.create.call_args
        inputs = kwargs.get("input")
        self.assertEqual(len(inputs), 2)
        self.assertIsInstance(inputs[0], ImageContent)
        self.assertIsInstance(inputs[1], TextContent)
        self.assertEqual(inputs[1].text, "Describe this image")
