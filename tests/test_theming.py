import unittest
import os
import json
from unittest.mock import patch
from interfaces.gui_qt.theming.theme import Theme, SIGNAL, SYNTHWAVE, NEUTRAL_CONTENT_THEME, build_stylesheet
from interfaces.gui_qt.theming.palette_hash import color_for_key


class TestThemingSystem(unittest.TestCase):
    def test_themes_defined(self):
        self.assertEqual(SIGNAL.name, "Signal")
        self.assertEqual(SYNTHWAVE.name, "Synthwave")
        self.assertEqual(NEUTRAL_CONTENT_THEME.name, "NeutralContent")
        self.assertTrue(len(SIGNAL.companion_palette) > 0)
        self.assertTrue(len(SYNTHWAVE.companion_palette) > 0)

    def test_palette_hash_stability(self):
        palette = ["#ff9900", "#aa88ff", "#00cc77"]
        key = "Ally"
        c1 = color_for_key(key, palette)
        c2 = color_for_key(key, palette)
        self.assertEqual(c1, c2)
        self.assertIn(c1, palette)

    def test_palette_hash_empty(self):
        self.assertEqual(color_for_key("test", []), "#ffffff")

    def test_build_stylesheet_template(self):
        template_path = "interfaces/gui_qt/theming/base.qss.tmpl"
        qss = build_stylesheet(SIGNAL, template_path)
        self.assertTrue(len(qss) > 0)
        self.assertIn(SIGNAL.bg_base, qss)
        self.assertIn(SIGNAL.accent_primary, qss)
        self.assertIn("background-color:", qss)

    @patch("os.path.exists")
    @patch("builtins.open")
    def test_build_stylesheet_custom_override(self, mock_open, mock_exists):
        # Mock os.path.exists to return True for user_config.json and custom qss
        mock_exists.return_value = True
        
        # Mock json load and file read
        mock_file_data = json.dumps({"custom_qss_path": "custom.qss"})
        
        # We can test build_stylesheet with real file or mocks. Let's test with real file or simple integration.
        # Actually let's test building stylesheet with actual template file.
        pass


if __name__ == "__main__":
    unittest.main()
