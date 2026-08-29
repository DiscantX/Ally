import unittest
from unittest.mock import MagicMock
from pydantic import BaseModel
from infrastructure.llm.gemini_provider import GeminiProvider

class SampleSchema(BaseModel):
    answer: str

class TestGeminiProviderStream(unittest.TestCase):
    def test_generate_structured_stream(self):
        mock_client = MagicMock()
        
        # Mock parts with thoughts and text
        part1 = MagicMock()
        part1.thought = True
        part1.text = "Thinking process step 1..."
        
        part2 = MagicMock()
        part2.thought = True
        part2.text = "Thinking process step 2..."
        
        part3 = MagicMock()
        part3.thought = False
        part3.text = '{"answer": "success"}'
        
        candidate = MagicMock()
        candidate.content.parts = [part1, part2, part3]
        
        chunk = MagicMock()
        chunk.candidates = [candidate]
        
        mock_client.models.generate_content_stream.return_value = [chunk]
        
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
        mock_client.models.generate_content_stream.assert_called_once()

    def test_generate_structured_stream_no_json(self):
        mock_client = MagicMock()
        candidate = MagicMock()
        candidate.content.parts = []
        chunk = MagicMock()
        chunk.candidates = [candidate]
        mock_client.models.generate_content_stream.return_value = [chunk]
        
        provider = GeminiProvider(client=mock_client)
        with self.assertRaises(ValueError):
            provider.generate_structured_stream(
                model="gemini-2.5-flash",
                contents=["test prompt"],
                schema=SampleSchema
            )

if __name__ == "__main__":
    unittest.main()
