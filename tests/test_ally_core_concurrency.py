"""Tests for AllyCore thread safety and initialization."""
import threading
import time
import unittest
from unittest.mock import MagicMock, patch


class TestAllyCoreConcurrency(unittest.TestCase):
    def test_state_lock_exists(self):
        """Verify that AllyCore has a state_lock attribute that is an RLock."""
        # Import only what we need and mock the rest
        import sys
        from unittest.mock import MagicMock
        
        # Mock all the problematic dependencies
        sys.modules['cv2'] = MagicMock()
        sys.modules['PIL'] = MagicMock()
        sys.modules['PIL.Image'] = MagicMock()
        sys.modules['google'] = MagicMock()
        sys.modules['google.genai'] = MagicMock()
        sys.modules['partial_json_parser'] = MagicMock()
        sys.modules['mss'] = MagicMock()
        sys.modules['pyaudio'] = MagicMock()
        sys.modules['win32con'] = MagicMock()
        sys.modules['win32gui'] = MagicMock()
        sys.modules['pygetwindow'] = MagicMock()
        
        # Now we can import
        from brain.reasoning.core import AllyCore
        
        # Create a minimal instance
        core = AllyCore(image_path="test.png")
        
        # Verify state_lock exists and is an RLock
        self.assertTrue(hasattr(core, 'state_lock'))
        self.assertIsInstance(core.state_lock, threading.RLock)

    def test_initialization_lock_exists(self):
        """Verify that AllyCore has an initialization lock."""
        import sys
        from unittest.mock import MagicMock
        
        # Mock all the problematic dependencies
        sys.modules['cv2'] = MagicMock()
        sys.modules['PIL'] = MagicMock()
        sys.modules['PIL.Image'] = MagicMock()
        sys.modules['google'] = MagicMock()
        sys.modules['google.genai'] = MagicMock()
        sys.modules['partial_json_parser'] = MagicMock()
        sys.modules['mss'] = MagicMock()
        sys.modules['pyaudio'] = MagicMock()
        sys.modules['win32con'] = MagicMock()
        sys.modules['win32gui'] = MagicMock()
        sys.modules['pygetwindow'] = MagicMock()
        
        from brain.reasoning.core import AllyCore
        
        core = AllyCore(image_path="test.png")
        
        # Verify _initialization_lock exists and is an RLock
        self.assertTrue(hasattr(core, '_initialization_lock'))
        self.assertIsInstance(core._initialization_lock, threading.RLock)
        
        # Verify _initialized flag exists
        self.assertTrue(hasattr(core, '_initialized'))

    def test_sandbox_has_lock(self):
        """Verify that sandbox has its own lock."""
        import sys
        from unittest.mock import MagicMock
        
        # Mock all the problematic dependencies
        sys.modules['cv2'] = MagicMock()
        sys.modules['PIL'] = MagicMock()
        sys.modules['PIL.Image'] = MagicMock()
        sys.modules['google'] = MagicMock()
        sys.modules['google.genai'] = MagicMock()
        sys.modules['partial_json_parser'] = MagicMock()
        sys.modules['mss'] = MagicMock()
        sys.modules['pyaudio'] = MagicMock()
        sys.modules['win32con'] = MagicMock()
        sys.modules['win32gui'] = MagicMock()
        sys.modules['pygetwindow'] = MagicMock()
        
        from brain.reasoning.core import AllyCore
        
        core = AllyCore(image_path="test.png")
        
        # Verify sandbox has a lock
        self.assertTrue(hasattr(core.sandbox, '_lock'))
        self.assertIsInstance(core.sandbox._lock, threading.RLock)


if __name__ == "__main__":
    unittest.main()
