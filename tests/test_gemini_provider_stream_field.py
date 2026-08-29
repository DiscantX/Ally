import unittest
from unittest.mock import MagicMock, patch
from pydantic import BaseModel
from google.genai import errors
from infrastructure.llm.gemini_provider import GeminiProvider

class AnalysisSchema(BaseModel):
    analysis: str

class TestGeminiProviderStreamField(unittest.TestCase):
    def test_generate_structured_stream_field_success(self):
        mock_client = MagicMock()
        
        # Simulate chunks splitting JSON and analysis value mid-word
        part1 = MagicMock()
        part1.text = '{"analysis": "Hel'
        part2 = MagicMock()
        part2.text = 'lo ther'
        part3 = MagicMock()
        part3.text = 'e, friend!"}'
        
        c1 = MagicMock()
        c1.candidates = [MagicMock(content=MagicMock(parts=[part1]))]
        c2 = MagicMock()
        c2.candidates = [MagicMock(content=MagicMock(parts=[part2]))]
        c3 = MagicMock()
        c3.candidates = [MagicMock(content=MagicMock(parts=[part3]))]
        
        mock_client.models.generate_content_stream.return_value = [c1, c2, c3]
        
        provider = GeminiProvider(client=mock_client)
        
        emitted_chunks = []
        def on_chunk(text: str):
            emitted_chunks.append(text)
            
        result = provider.generate_structured_stream_field(
            model="gemini-2.5-flash",
            contents=["test prompt"],
            schema=AnalysisSchema,
            stream_field="analysis",
            on_field_chunk=on_chunk
        )
        
        self.assertEqual(result.analysis, "Hello there, friend!")
        full_reconstructed = "".join(emitted_chunks)
        self.assertEqual(full_reconstructed, "Hello there, friend!")
        mock_client.models.generate_content_stream.assert_called_once()

    def test_generate_structured_stream_field_no_content(self):
        mock_client = MagicMock()
        c1 = MagicMock()
        c1.candidates = [MagicMock(content=MagicMock(parts=[]))]
        mock_client.models.generate_content_stream.return_value = [c1]
        
        provider = GeminiProvider(client=mock_client)
        with self.assertRaises(ValueError):
            provider.generate_structured_stream_field(
                model="gemini-2.5-flash",
                contents=["test prompt"],
                schema=AnalysisSchema,
                stream_field="analysis"
            )

    @patch("infrastructure.llm.gemini_provider.partial_json_parser")
    def test_generate_structured_stream_field_parse_exception_handling(self, mock_pjp):
        mock_client = MagicMock()
        part1 = MagicMock()
        part1.text = '{"analysis": "first"}'
        c1 = MagicMock()
        c1.candidates = [MagicMock(content=MagicMock(parts=[part1]))]
        mock_client.models.generate_content_stream.return_value = [c1]

        # Make loads raise on first call, succeed on second (or vice versa)
        original_loads = mock_pjp.loads
        call_count = [0]
        def side_effect(buf, allow):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("transient parse failure")
            return original_loads(buf, allow)

        mock_pjp.loads.side_effect = side_effect
        mock_pjp.Allow.ALL = 511

        provider = GeminiProvider(client=mock_client)
        emitted = []
        result = provider.generate_structured_stream_field(
            model="model",
            contents=["prompt"],
            schema=AnalysisSchema,
            stream_field="analysis",
            on_field_chunk=lambda t: emitted.append(t)
        )
        self.assertEqual(result.analysis, "first")

    def test_retry_with_reset(self):
        mock_client = MagicMock()
        
        # First attempt fails with ClientError after one chunk
        part1 = MagicMock()
        part1.text = '{"analysis": "bad'
        c1 = MagicMock()
        c1.candidates = [MagicMock(content=MagicMock(parts=[part1]))]
        
        # Second attempt succeeds cleanly
        part2 = MagicMock()
        part2.text = '{"analysis": "success"}'
        c2 = MagicMock()
        c2.candidates = [MagicMock(content=MagicMock(parts=[part2]))]
        
        # We can make generate_content_stream raise on first iteration of first call, or raise ClientError
        def stream_side_effect(*args, **kwargs):
            if stream_side_effect.called:
                return [c2]
            stream_side_effect.called = True
            # yield one chunk that calls on_field_chunk, then raise ClientError
            def generator():
                yield c1
                raise errors.ClientError(429, {})
            return generator()
        stream_side_effect.called = False

        mock_client.models.generate_content_stream.side_effect = stream_side_effect

        provider = GeminiProvider(client=mock_client)
        
        emitted = []
        resets = []
        
        result = provider.generate_structured_stream_field(
            model="model",
            contents=["prompt"],
            schema=AnalysisSchema,
            stream_field="analysis",
            on_field_chunk=lambda t: emitted.append(t),
            on_stream_reset=lambda: resets.append(True),
            max_retries=3
        )
        
        self.assertEqual(result.analysis, "success")
        self.assertEqual(len(resets), 1)
        self.assertIn("success", "".join(emitted))

    def test_optional_callbacks(self):
        mock_client = MagicMock()
        part1 = MagicMock()
        part1.text = '{"analysis": "ok"}'
        c1 = MagicMock()
        c1.candidates = [MagicMock(content=MagicMock(parts=[part1]))]
        mock_client.models.generate_content_stream.return_value = [c1]

        provider = GeminiProvider(client=mock_client)
        result = provider.generate_structured_stream_field(
            model="model",
            contents=["prompt"],
            schema=AnalysisSchema,
            stream_field="analysis",
            on_field_chunk=None,
            on_stream_reset=None
        )
        self.assertEqual(result.analysis, "ok")

if __name__ == "__main__":
    unittest.main()
