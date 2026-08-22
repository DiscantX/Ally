"""Test script for MTGA Entity and Enum Resolvers."""

import os
import tempfile
import unittest
import json
import gzip

from plugins.mtga.resolver import EnumResolver, EntityResolver


class TestMTGAResolvers(unittest.TestCase):

    def test_enum_resolver_phases(self):
        self.assertEqual(EnumResolver.resolve_phase(1), "Beginning")
        self.assertEqual(EnumResolver.resolve_phase(2), "Main1")
        self.assertEqual(EnumResolver.resolve_phase(99), "UnknownPhase(99)")
        self.assertEqual(EnumResolver.resolve_phase("Main1"), "Main1")

    def test_enum_resolver_steps(self):
        self.assertEqual(EnumResolver.resolve_step(1), "Untap")
        self.assertEqual(EnumResolver.resolve_step(5), "DeclareAttack")
        self.assertEqual(EnumResolver.resolve_step(99), "UnknownStep(99)")

    def test_enum_resolver_zones(self):
        self.assertEqual(EnumResolver.resolve_zone(1), "Library")
        self.assertEqual(EnumResolver.resolve_zone(3), "Battlefield")
        self.assertEqual(EnumResolver.resolve_zone(99), "UnknownZone(99)")

    def test_enum_resolver_colors(self):
        self.assertEqual(EnumResolver.resolve_color(1), "White")
        self.assertEqual(EnumResolver.resolve_color(4), "Red")

    def test_entity_resolver_fallback(self):
        resolver = EntityResolver(data_dir="nonexistent_path_abc")
        card = resolver.resolve_card(12345)
        self.assertEqual(card["grpId"], 12345)
        self.assertEqual(card["name"], "Card(12345)")
        self.assertEqual(card["type"], "Unknown")

    def test_entity_resolver_with_local_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock data_cards_abc123.mtga (JSON or Gzip JSON)
            cards_data = [
                {"grpId": 1001, "titleId": 5001, "cardType": "CardType_Creature", "color": ["CardColor_Red"]}
            ]
            loc_data = [
                {"id": 5001, "text": "Goblin Guide"}
            ]

            cards_path = os.path.join(tmpdir, "data_cards_abc123.mtga")
            loc_path = os.path.join(tmpdir, "data_loc_abc123.mtga")

            with open(cards_path, "wb") as f:
                f.write(gzip.compress(json.dumps(cards_data).encode("utf-8")))

            with open(loc_path, "wb") as f:
                f.write(json.dumps(loc_data).encode("utf-8"))

            resolver = EntityResolver(data_dir=tmpdir)
            card = resolver.resolve_card(1001)
            self.assertEqual(card["grpId"], 1001)
            self.assertEqual(card["name"], "Goblin Guide")
            self.assertEqual(card["type"], "CardType_Creature")
            self.assertEqual(card["colors"], ["CardColor_Red"])


if __name__ == "__main__":
    unittest.main()
