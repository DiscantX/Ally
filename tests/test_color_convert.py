"""Unit tests for theming/color_convert.py
"""
import unittest
from theming.color_convert import hex_to_ansi_fg, ansi_fg_to_hex


class TestColorConvert(unittest.TestCase):
    def test_hex_to_ansi_fg_roundtrip(self):
        hex_in = "#ff2ddc"
        ansi_body = hex_to_ansi_fg(hex_in)
        self.assertEqual(ansi_body, "38;2;255;45;220")
        hex_out = ansi_fg_to_hex(ansi_body)
        self.assertEqual(hex_out.lower(), hex_in.lower())

    def test_ansi_fg_to_hex_cube(self):
        ansi_code = "38;5;208"
        hex_val = ansi_fg_to_hex(ansi_code)
        self.assertEqual(hex_val.lower(), "#ff8700")

    def test_ansi_fg_to_hex_grayscale(self):
        ansi_code = "38;5;232"
        hex_val = ansi_fg_to_hex(ansi_code)
        self.assertEqual(hex_val.lower(), "#080808")

    def test_ansi_fg_to_hex_invalid_low_index(self):
        with self.assertRaises(ValueError):
            ansi_fg_to_hex("38;5;15")

    def test_invalid_hex(self):
        with self.assertRaises(ValueError):
            hex_to_ansi_fg("invalid")


if __name__ == "__main__":
    unittest.main()
