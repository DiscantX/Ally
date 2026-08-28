"""Tests for MTGA full/diff state accumulation over raw Arena IDs."""

import collections
import unittest

from ingestion.plugins.mtga.parser import MTGALogParser


SAMPLE_LOG = "docs/log-single-game.log"


class StubEntityResolver:
    def resolve_card(self, grp_id: int, **kwargs) -> dict:
        return {
            "grpId": grp_id,
            "name": f"Card({grp_id})",
            "type": "Unknown",
            "colors": [],
            "source": "stub",
        }


def parse_sample() -> MTGALogParser:
    parser = MTGALogParser(SAMPLE_LOG)
    parser.entity_resolver = StubEntityResolver()
    list(parser.parse())
    return parser


def zone_reference_stats(parser: MTGALogParser) -> dict:
    state = parser.game_state
    references = []
    missing = []
    mismatches = []

    for zone_id, zone in state["zones"].items():
        for object_id in zone.get("objectInstanceIds", []):
            references.append((zone_id, object_id))
            obj = state["game_objects"].get(object_id)
            if obj is None:
                missing.append((zone_id, object_id))
            elif obj.get("zoneId") != zone_id:
                mismatches.append((zone_id, object_id, obj.get("zoneId")))

    reference_counts = collections.Counter(
        object_id for _, object_id in references
    )
    duplicates = {
        object_id: count
        for object_id, count in reference_counts.items()
        if count > 1
    }

    return {
        "references": references,
        "missing": missing,
        "mismatches": mismatches,
        "duplicates": duplicates,
    }


class TestMTGAAccumulator(unittest.TestCase):
    def test_final_state_counts_raw_objects_and_zones(self):
        parser = parse_sample()

        self.assertEqual(len(parser.game_state["game_objects"]), 171)
        self.assertEqual(len(parser.game_state["zones"]), 17)

    def test_described_objects_match_their_zone_membership(self):
        parser = parse_sample()

        stats = zone_reference_stats(parser)

        self.assertEqual(len(stats["references"]), 198)
        self.assertEqual(len(stats["missing"]), 99)
        self.assertEqual(stats["mismatches"], [])
        self.assertEqual(stats["duplicates"], {})

    def test_object_id_changes_remove_old_zone_membership(self):
        parser = parse_sample()

        zones = parser.game_state["zones"]
        object_557_zones = [
            zone_id
            for zone_id, zone in zones.items()
            if 557 in zone.get("objectInstanceIds", [])
        ]
        object_228_zones = [
            zone_id
            for zone_id, zone in zones.items()
            if 228 in zone.get("objectInstanceIds", [])
        ]

        self.assertEqual(object_557_zones, [30])
        self.assertEqual(object_228_zones, [30])
        self.assertNotIn(228, zones[35].get("objectInstanceIds", []))

    def test_known_final_zones_for_public_objects(self):
        parser = parse_sample()
        objects = parser.game_state["game_objects"]

        self.assertEqual(objects[557]["zoneId"], 30)
        self.assertEqual(objects[559]["zoneId"], 37)
        self.assertEqual(objects[545]["zoneId"], 28)


if __name__ == "__main__":
    unittest.main()
