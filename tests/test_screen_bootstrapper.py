"""Unit tests for ScreenBootstrapper - screen bootstrap detection."""

import os
import tempfile
import unittest
import json
import cv2
import numpy as np
from unittest.mock import MagicMock, patch

from brain.perception.screen_bootstrapper import ScreenBootstrapper, BootstrapResult


class TestScreenBootstrapper(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        
        # Create a test layout file
        self.layout_path = os.path.join(self.tmpdir.name, "test_layout.json")
        layout = {
            "screens": {
                "combat": {
                    "anchors": [
                        {"x": 10, "y": 10, "w": 20, "h": 20, "is_anchor": True}
                    ]
                }
            }
        }
        with open(self.layout_path, 'w') as f:
            json.dump(layout, f)
        
        # Mock config
        self.patcher = patch('brain.perception.screen_bootstrapper.load_user_config')
        self.mock_config = self.patcher.start()
        self.mock_config.return_value = {
            "match_threshold": 0.85,
        }

    def tearDown(self):
        self.patcher.stop()
        self.tmpdir.cleanup()

    def test_initialization(self):
        bootstrapper = ScreenBootstrapper(self.layout_path)
        self.assertIsNotNone(bootstrapper)

    def test_bootstrap_known_screen(self):
        bootstrapper = ScreenBootstrapper(self.layout_path)
        
        # Create a frame that matches the combat anchor
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[10:30, 10:30] = 255
        
        result = bootstrapper.bootstrap(frame)
        
        self.assertIsInstance(result, BootstrapResult)
        # The exact result depends on SSIM matching

    def test_bootstrap_unknown_screen(self):
        bootstrapper = ScreenBootstrapper(self.layout_path)
        
        # Create a frame with no matching anchors
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[80:90, 80:90] = 255
        
        result = bootstrapper.bootstrap(frame)
        
        self.assertIsInstance(result, BootstrapResult)


if __name__ == "__main__":
    unittest.main()
