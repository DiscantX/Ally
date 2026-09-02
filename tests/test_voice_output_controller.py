"""Unit tests for VoiceOutputController - TTS voice output."""

import unittest
from unittest.mock import MagicMock, patch

from brain.reasoning.voice_output_controller import VoiceOutputController


class TestVoiceOutputController(unittest.TestCase):
    def setUp(self):
        # Mock provider
        self.mock_tts_provider = MagicMock()
        self.mock_tts_provider.synthesize_speech.return_value = b"test audio"
        
        # Mock config
        self.patcher = patch('brain.reasoning.voice_output_controller.load_user_config')
        self.mock_config = self.patcher.start()
        self.mock_config.return_value = {
            "voice_output_enabled": True,
            "tts_model": "gemini-3.1-flash-tts-preview",
            "tts_voice": "Kore",
            "tts_sample_rate": 24000,
        }

    def tearDown(self):
        self.patcher.stop()

    def test_initialization(self):
        controller = VoiceOutputController(tts_provider=self.mock_tts_provider)
        self.assertIsNotNone(controller)

    def test_speak(self):
        controller = VoiceOutputController(tts_provider=self.mock_tts_provider)
        
        result = controller.speak("Hello, this is a test")
        
        # Should return audio data
        self.assertIsNotNone(result)
        self.mock_tts_provider.synthesize_speech.assert_called_once()

    def test_speak_disabled(self):
        self.mock_config.return_value = {
            "voice_output_enabled": False,
            "tts_model": "gemini-3.1-flash-tts-preview",
            "tts_voice": "Kore",
            "tts_sample_rate": 24000,
        }
        
        controller = VoiceOutputController(tts_provider=self.mock_tts_provider)
        
        result = controller.speak("Hello, this is a test")
        
        # Should return None when disabled
        self.assertIsNone(result)
        self.mock_tts_provider.synthesize_speech.assert_not_called()

    def test_speak_empty_text(self):
        controller = VoiceOutputController(tts_provider=self.mock_tts_provider)
        
        result = controller.speak("")
        
        # Should return None for empty text
        self.assertIsNone(result)
        self.mock_tts_provider.synthesize_speech.assert_not_called()


if __name__ == "__main__":
    unittest.main()
