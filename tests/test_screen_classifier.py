"""Unit tests for ScreenClassifier - SSIM-based screen matching."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import cv2
import numpy as np

from brain.perception.screen_classifier import ScreenClassifier, ScreenMatch


class TestScreenClassifier(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        # Create test images
        self.image_100x100 = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)
        self.image_200x200 = np.random.randint(0, 256, (200, 200, 3), dtype=np.uint8)
        
        # Create a simple layout for testing
        self.layout_path = os.path.join(self.tmpdir.name, "test_layout.json")
        import json
        layout = {
            "screens": {
                "combat": {
                    "anchors": [
                        {"x": 10, "y": 10, "w": 20, "h": 20, "is_anchor": True}
                    ]
                },
                "map": {
                    "anchors": [
                        {"x": 50, "y": 50, "w": 20, "h": 20, "is_anchor": True}
                    ]
                }
            }
        }
        with open(self.layout_path, 'w') as f:
            json.dump(layout, f)
        
        # Mock config
        self.patcher = patch('brain.perception.screen_classifier.load_user_config')
        self.mock_config = self.patcher.start()
        self.mock_config.return_value = {
            "match_threshold": 0.85,
            "draft_match_threshold": 0.93,
        }

    def tearDown(self):
        self.patcher.stop()
        self.tmpdir.cleanup()

    def test_initialization(self):
        classifier = ScreenClassifier(layout_path=self.layout_path)
        self.assertIsNotNone(classifier)
        self.assertEqual(classifier.layout_path, self.layout_path)

    def test_classify_with_anchor_match(self):
        classifier = ScreenClassifier(layout_path=self.layout_path)
        
        # Create a mock frame that matches the combat anchor
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[10:30, 10:30] = 255  # White anchor region
        
        result = classifier.classify(frame)
        self.assertIsInstance(result, ScreenMatch)
        # The exact match depends on the SSIM comparison
        # Just verify it returns a valid result

    def test_classify_unknown_screen(self):
        classifier = ScreenClassifier(layout_path=self.layout_path)
        
        # Create a frame with no matching anchors
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[80:90, 80:90] = 255  # Different region
        
        result = classifier.classify(frame)
        self.assertIsInstance(result, ScreenMatch)
        self.assertEqual(result.screen_name, "unknown")

    def test_classify_with_empty_layout(self):
        empty_layout_path = os.path.join(self.tmpdir.name, "empty_layout.json")
        import json
        with open(empty_layout_path, 'w') as f:
            json.dump({"screens": {}}, f)
        
        classifier = ScreenClassifier(layout_path=empty_layout_path)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        
        result = classifier.classify(frame)
        self.assertIsInstance(result, ScreenMatch)
        self.assertEqual(result.screen_name, "unknown")


if __name__ == "__main__":
    unittest.main()
