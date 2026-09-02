"""Unit tests for LayoutManager - UI layout management."""

import os
import tempfile
import unittest
import json

from brain.perception.layout import LayoutManager, UIElement


class TestLayoutManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        
        # Create a test layout file
        self.layout_path = os.path.join(self.tmpdir.name, "test_layout.json")
        layout = {
            "screens": {
                "combat": {
                    "elements": [
                        {"id": "health_bar", "label": "Health", "x": 10, "y": 10, "w": 100, "h": 20},
                        {"id": "mana_bar", "label": "Mana", "x": 10, "y": 40, "w": 100, "h": 20}
                    ]
                },
                "map": {
                    "elements": [
                        {"id": "minimap", "label": "Minimap", "x": 50, "y": 50, "w": 50, "h": 50}
                    ]
                }
            }
        }
        with open(self.layout_path, 'w') as f:
            json.dump(layout, f)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_layout(self):
        manager = LayoutManager(self.layout_path)
        self.assertIsNotNone(manager)
        self.assertEqual(manager.layout_path, self.layout_path)

    def test_get_elements_for_screen(self):
        manager = LayoutManager(self.layout_path)
        
        elements = manager.get_elements("combat")
        self.assertEqual(len(elements), 2)
        
        # Check element properties
        health_bar = [e for e in elements if e.id == "health_bar"][0]
        self.assertEqual(health_bar.label, "Health")
        self.assertEqual(health_bar.x, 10)
        self.assertEqual(health_bar.y, 10)

    def test_get_elements_unknown_screen(self):
        manager = LayoutManager(self.layout_path)
        
        elements = manager.get_elements("unknown_screen")
        self.assertEqual(len(elements), 0)

    def test_get_screen_names(self):
        manager = LayoutManager(self.layout_path)
        
        screens = manager.get_screen_names()
        self.assertIn("combat", screens)
        self.assertIn("map", screens)
        self.assertEqual(len(screens), 2)

    def test_add_element(self):
        manager = LayoutManager(self.layout_path)
        
        new_element = UIElement(id="new_btn", label="New Button", x=200, y=200, w=40, h=20)
        manager.add_element("combat", new_element)
        
        elements = manager.get_elements("combat")
        self.assertEqual(len(elements), 3)

    def test_save_layout(self):
        manager = LayoutManager(self.layout_path)
        
        new_element = UIElement(id="new_btn", label="New Button", x=200, y=200, w=40, h=20)
        manager.add_element("combat", new_element)
        
        # Save to a new file
        new_path = os.path.join(self.tmpdir.name, "new_layout.json")
        manager.save(new_path)
        
        # Verify the file was created and contains the new element
        self.assertTrue(os.path.exists(new_path))
        with open(new_path) as f:
            saved_layout = json.load(f)
        
        combat_elements = saved_layout["screens"]["combat"]["elements"]
        self.assertEqual(len(combat_elements), 3)


if __name__ == "__main__":
    unittest.main()
