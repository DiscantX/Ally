"""Unit tests for LayoutOCRReader - OCR layout reading."""

import unittest
from unittest.mock import MagicMock, patch
import cv2
import numpy as np

from brain.perception.layout_reader import LayoutOCRReader


class TestLayoutOCRReader(unittest.TestCase):
    def setUp(self):
        # Mock config
        self.patcher = patch('brain.perception.layout_reader.load_user_config')
        self.mock_config = self.patcher.start()
        self.mock_config.return_value = {}

    def tearDown(self):
        self.patcher.stop()

    def test_initialization(self):
        reader = LayoutOCRReader()
        self.assertIsNotNone(reader)

    @patch('brain.perception.layout_reader.cv2')
    def test_read_region(self, mock_cv2):
        reader = LayoutOCRReader()
        
        # Create a mock image
        mock_image = np.zeros((100, 100, 3), dtype=np.uint8)
        
        # Mock OCR result
        mock_cv2.image = MagicMock(return_value=mock_image)
        
        # This test is limited without actual OCR dependencies
        # Just verify the method can be called
        result = reader.read_region(mock_image, 10, 10, 20, 20)
        # Result depends on OCR implementation


if __name__ == "__main__":
    unittest.main()
