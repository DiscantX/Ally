"""Test script for MTGA Entity and Enum Resolvers."""

import os
import tempfile
import unittest
import sqlite3

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

    def test_entity_resolver_with_sqlite_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Raw_CardDatabase_test123.mtga")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE Cards (grpId INTEGER, name TEXT, type TEXT)")
            cursor.execute("INSERT INTO Cards VALUES (?, ?, ?)", (1001, "Lightning Bolt", "Instant"))
            cursor.execute("CREATE TABLE Localization (id INTEGER, text TEXT)")
            cursor.execute("INSERT INTO Localization VALUES (?, ?)", (5001, "Lightning Bolt"))
            conn.commit()
            conn.close()

            resolver = EntityResolver(data_dir=tmpdir)
            card = resolver.resolve_card(1001)
            self.assertEqual(card["grpId"], 1001)
            self.assertEqual(card["name"], "Lightning Bolt")
            self.assertEqual(card["type"], "Instant")


if __name__ == "__main__":
    unittest.main()
