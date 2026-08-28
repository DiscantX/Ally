"""Integration test: real EntityResolver + real captured log, checked
together. The existing test suites check these in isolation (resolver
against a fake DB, parser structure against a stub resolver) -- this is
the one that would actually catch a schema drift or an ID that doesn't
resolve, since it exercises the full path a live Collector will use.

Skips cleanly wherever the real DB or the real log isn't available (e.g.
CI, or Ficus's dev machine without both artifacts present), the same
pattern as test_resolver.py's local-schema test.
"""

import os
import unittest

from ingestion.plugins.mtga.parser import MTGALogParser
from ingestion.plugins.mtga.resolver import EntityResolver

SAMPLE_LOG = "docs/log-single-game.log"

# Minimum acceptable resolution rate before this is treated as a real
# regression rather than "this log has a couple of tokens/emblems in it."
MIN_RESOLUTION_RATE = 0.90


class TestNameResolutionIntegration(unittest.TestCase):
    def setUp(self):
        resolver = EntityResolver()
        if not os.path.isdir(resolver.data_dir) or not resolver.load_data():
            self.skipTest("local MTGA card database not available")
        if not os.path.exists(SAMPLE_LOG):
            self.skipTest(f"sample log not found at {SAMPLE_LOG}")

    def test_final_state_objects_resolve_against_real_db(self):
        parser = MTGALogParser(SAMPLE_LOG)  # real EntityResolver by default
        list(parser.parse())

        objects_with_grp_id = {
            obj_id: obj
            for obj_id, obj in parser.game_state["game_objects"].items()
            if obj.get("resolved_card") is not None
        }
        self.assertGreater(
            len(objects_with_grp_id), 0,
            "No game objects carried a resolved_card at all -- parser/resolver "
            "wiring is broken, not just a resolution-rate issue.",
        )

        resolved = [
            obj for obj in objects_with_grp_id.values()
            if obj["resolved_card"]["source"] == "arena_db"
        ]
        rate = len(resolved) / len(objects_with_grp_id)
        self.assertGreaterEqual(
            rate, MIN_RESOLUTION_RATE,
            f"Only {rate:.0%} of objects resolved to real card data "
            f"(threshold {MIN_RESOLUTION_RATE:.0%}) -- check for a schema "
            f"drift or a stale local DB snapshot.",
        )

    def test_resolved_zones_carry_real_names_not_placeholders(self):
        parser = MTGALogParser(SAMPLE_LOG)
        list(parser.parse())

        resolved_zones: dict = parser.get_resolved_zones()
        placeholder_names = [
            obj["resolved_card"]["name"]
            for zone in resolved_zones.values()
            for obj in zone["objects"]
            if obj.get("resolved_card") and obj["resolved_card"]["name"].startswith("Card(")
        ]
        total_named = sum(
            1
            for zone in resolved_zones.values()
            for obj in zone["objects"]
            if obj.get("resolved_card")
        )
        if total_named:
            placeholder_rate = len(placeholder_names) / total_named
            self.assertLess(
                placeholder_rate, 1 - MIN_RESOLUTION_RATE,
                f"{len(placeholder_names)}/{total_named} zone objects still show "
                f"placeholder 'Card(N)' names: {placeholder_names[:10]}",
            )

    def test_every_object_with_grpid_has_resolved_card_or_source_card(self):
        parser = MTGALogParser(SAMPLE_LOG)
        list(parser.parse())

        uncovered = []
        for obj_id, obj in parser.game_state["game_objects"].items():
            if obj.get("grpId") is not None:
                if obj.get("resolved_card") is None and obj.get("resolved_source_card") is None:
                    uncovered.append((obj_id, obj.get("type"), obj.get("grpId")))

        self.assertEqual(
            len(uncovered), 0,
            f"Objects with grpId fell through without either resolved_card or resolved_source_card: {uncovered}"
        )


if __name__ == "__main__":
    unittest.main()
