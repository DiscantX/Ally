"""Unit tests for ChangeDetector - frame-to-frame difference detection."""

import unittest
import numpy as np
from unittest.mock import patch

from brain.perception.change_detector import ChangeDetector


class TestChangeDetector(unittest.TestCase):
    def setUp(self):
        # Mock config
        self.patcher = patch('brain.perception.change_detector.load_user_config')
        self.mock_config = self.patcher.start()
        self.mock_config.return_value = {
            "threshold_percent": 15,
            "pixel_diff_threshold": 25,
            "enable_cooldown": True,
            "cooldown_seconds": 2.0,
            "major_change_threshold": 50.0,
            "enable_stability_check": True,
            "stability_threshold_percent": 2.0,
            "use_ssim": True,
            "unknown_streak_threshold": 3,
            "enable_downscaling": True,
        }

    def tearDown(self):
        self.patcher.stop()

    def test_initialization(self):
        detector = ChangeDetector()
        self.assertIsNotNone(detector)
        self.assertEqual(detector.threshold_percent, 15)
        self.assertEqual(detector.pixel_diff_threshold, 25)

    def test_detect_change_significant_difference(self):
        detector = ChangeDetector()
        
        # Create two very different frames
        frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
        frame2 = np.ones((100, 100, 3), dtype=np.uint8) * 255
        
        result = detector.detect_change(frame1, frame2)
        self.assertTrue(result.has_changed)

    def test_detect_change_no_difference(self):
        detector = ChangeDetector()
        
        # Create two identical frames
        frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
        frame2 = np.zeros((100, 100, 3), dtype=np.uint8)
        
        result = detector.detect_change(frame1, frame2)
        self.assertFalse(result.has_changed)

    def test_detect_change_minor_difference(self):
        detector = ChangeDetector(threshold_percent=10)
        
        # Create frames with minor difference (below threshold)
        frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
        frame2 = np.zeros((100, 100, 3), dtype=np.uint8)
        # Change only 5% of pixels
        frame2[0:5, 0:10] = 255
        
        result = detector.detect_change(frame1, frame2)
        self.assertFalse(result.has_changed)

    def test_reset_streak(self):
        detector = ChangeDetector()
        
        # Simulate unknown streak
        detector.unknown_streak = 5
        detector.reset_streak()
        
        self.assertEqual(detector.unknown_streak, 0)


if __name__ == "__main__":
    unittest.main()
