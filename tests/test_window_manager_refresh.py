import unittest
from unittest.mock import patch, MagicMock

try:
    import win32gui
    _WIN32GUI_AVAILABLE = True
except ImportError:
    _WIN32GUI_AVAILABLE = False

from collectors.window_manager import ClientRect


@unittest.skipUnless(_WIN32GUI_AVAILABLE, "win32gui required for window manager tests")
class TestWindowManagerRefresh(unittest.TestCase):
    @patch("win32gui.FindWindow", return_value=123)
    @patch("win32gui.GetClientRect", return_value=(0, 0, 800, 600))
    @patch("win32gui.ClientToScreen", side_effect=lambda hwnd, pt: pt)
    @patch("win32gui.IsWindow", return_value=True)
    @patch("win32gui.GetForegroundWindow", return_value=123)
    def test_is_foreground_true(self, mock_fg, mock_is_win, mock_c2s, mock_gcr, mock_fw):
        client = ClientRect("Test Game")
        self.assertTrue(client.is_foreground())

    @patch("win32gui.FindWindow", return_value=123)
    @patch("win32gui.GetClientRect", return_value=(0, 0, 800, 600))
    @patch("win32gui.ClientToScreen", side_effect=lambda hwnd, pt: pt)
    @patch("win32gui.IsWindow", return_value=True)
    @patch("win32gui.GetForegroundWindow", return_value=456)
    def test_is_foreground_false(self, mock_fg, mock_is_win, mock_c2s, mock_gcr, mock_fw):
        client = ClientRect("Test Game")
        self.assertFalse(client.is_foreground())

    @patch("win32gui.FindWindow", return_value=123)
    @patch("win32gui.GetClientRect", return_value=(0, 0, 800, 600))
    @patch("win32gui.ClientToScreen", side_effect=lambda hwnd, pt: pt)
    @patch("win32gui.IsWindow", return_value=False)
    def test_refresh_window_gone(self, mock_is_win, mock_c2s, mock_gcr, mock_fw):
        client = ClientRect("Test Game")
        self.assertFalse(client.refresh())


if __name__ == "__main__":
    unittest.main()
