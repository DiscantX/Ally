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
        card = resolver.resolve_card(95660)
        self.assertEqual(card["grpId"], 95660)
        self.assertEqual(card["name"], "Card(95660)")
        self.assertEqual(card["type"], "Unknown")
        self.assertEqual(card["colors"], [])
        self.assertEqual(card["source"], "unresolved")

    def test_entity_resolver_with_sqlite_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Raw_CardDatabase_test123.mtga")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE Cards (GrpId INTEGER, TitleId INTEGER, TypeTextId INTEGER, Colors TEXT)"
            )
            cursor.execute(
                "INSERT INTO Cards VALUES (?, ?, ?, ?)",
                (1001, 5001, 6001, "4"),
            )
            cursor.execute(
                "CREATE TABLE Localizations_enUS (LocId INTEGER, Formatted INTEGER, Loc TEXT)"
            )
            cursor.execute(
                "INSERT INTO Localizations_enUS VALUES (?, ?, ?)",
                (5001, 1, "Lightning Bolt"),
            )
            cursor.execute(
                "INSERT INTO Localizations_enUS VALUES (?, ?, ?)",
                (6001, 1, "Instant"),
            )
            conn.commit()
            conn.close()

            resolver = EntityResolver(data_dir=tmpdir)
            card = resolver.resolve_card(1001)
            self.assertEqual(card["grpId"], 1001)
            self.assertEqual(card["name"], "Lightning Bolt")
            self.assertEqual(card["type"], "Instant")
            self.assertEqual(card["colors"], ["Red"])
            self.assertEqual(card["source"], "arena_db")

    def test_entity_resolver_against_local_arena_schema_when_available(self):
        resolver = EntityResolver()
        if not os.path.isdir(resolver.data_dir):
            self.skipTest("local MTGA data directory not available")
        if not resolver.load_data():
            self.skipTest("local MTGA card database not available")

        snakeskin_veil = resolver.resolve_card(93946)
        craterhoof = resolver.resolve_card(95660)
        forest = resolver.resolve_card(105182)

        self.assertEqual(snakeskin_veil["name"], "Snakeskin Veil")
        self.assertEqual(snakeskin_veil["type"], "Instant")
        self.assertEqual(snakeskin_veil["source"], "arena_db")
        self.assertEqual(craterhoof["name"], "Craterhoof Behemoth")
        self.assertEqual(craterhoof["type"], "Creature")
        self.assertEqual(craterhoof["source"], "arena_db")
        self.assertEqual(forest["name"], "Forest")
        self.assertEqual(forest["type"], "Basic Land")
        self.assertEqual(forest["source"], "arena_db")


if __name__ == "__main__":
    unittest.main()
