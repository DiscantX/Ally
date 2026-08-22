"""Tests for MTGA annotation normalization and semantic extraction."""

import collections
import unittest

from plugins.mtga.parser import MTGALogParser


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


class TestMTGAAnnotations(unittest.TestCase):
    def test_normalizes_annotation_type_names(self):
        self.assertEqual(
            MTGALogParser._normalize_annotation_type("AnnotationType_DamageDealt"),
            "DamageDealt",
        )
        self.assertEqual(MTGALogParser._normalize_annotation_type(48), "NewTurnStarted")
        self.assertEqual(
            MTGALogParser._normalize_annotation_type(999),
            "UnknownAnnotation(999)",
        )

    def test_counts_known_sample_annotations(self):
        parser = parse_sample()

        counts = collections.Counter(
            annotation_type
            for event in parser.events
            for annotation_type in event["types"]
        )

        self.assertEqual(len(parser.events), 845)
        self.assertEqual(counts["PhaseOrStepModified"], 141)
        self.assertEqual(counts["NewTurnStarted"], 13)
        self.assertEqual(counts["ZoneTransfer"], 57)
        self.assertEqual(counts["DamageDealt"], 40)

    def test_preserves_raw_annotation_type_names(self):
        parser = parse_sample()

        first_phase_event = next(
            event
            for event in parser.events
            if "PhaseOrStepModified" in event["types"]
        )

        self.assertEqual(first_phase_event["types"], ["PhaseOrStepModified"])
        self.assertEqual(
            first_phase_event["raw_types"],
            ["AnnotationType_PhaseOrStepModified"],
        )

    def test_phase_step_and_new_turn_state_updates(self):
        parser = parse_sample()

        turn_info = parser.game_state["turn_info"]

        self.assertEqual(turn_info["turn_event_count"], 13)
        self.assertEqual(turn_info["phase"], 3)
        self.assertEqual(turn_info["phase_name"], "Combat")
        self.assertEqual(turn_info["step"], 7)
        self.assertEqual(turn_info["step_name"], "CombatDamage")


if __name__ == "__main__":
    unittest.main()
