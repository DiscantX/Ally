"""Tests for MTGA log framing and match boundary parsing."""

import unittest

from plugins.mtga.parser import MTGALogParser


SAMPLE_LOG = "docs/log-single-game.log"


class StubEntityResolver:
    def resolve_card(self, grp_id: int) -> dict:
        return {
            "grpId": grp_id,
            "name": f"Card({grp_id})",
            "type": "Unknown",
            "colors": [],
            "source": "stub",
        }


class TestMTGALogFraming(unittest.TestCase):
    def test_iter_gre_payloads_counts_sample_payloads(self):
        parser = MTGALogParser(SAMPLE_LOG)

        payloads = list(parser.iter_gre_payloads())

        self.assertEqual(len(payloads), 271)

    def test_iter_gre_client_messages_counts_all_nested_messages(self):
        parser = MTGALogParser(SAMPLE_LOG)

        messages = list(parser.iter_gre_client_messages())
        game_states = [
            message["gameStateMessage"]
            for message in messages
            if "gameStateMessage" in message
        ]
        full_states = [
            message
            for message in game_states
            if message.get("type") == "GameStateType_Full"
        ]
        diff_states = [
            message
            for message in game_states
            if message.get("type") == "GameStateType_Diff"
        ]

        self.assertEqual(len(messages), 542)
        self.assertEqual(len(game_states), 328)
        self.assertEqual(len(full_states), 1)
        self.assertEqual(len(diff_states), 327)

    def test_parse_yields_every_game_state_message(self):
        parser = MTGALogParser(SAMPLE_LOG)
        parser.entity_resolver = StubEntityResolver()

        parsed_events = list(parser.parse())
        game_state_events = [
            event for event in parsed_events if event.get("type") == "game_state"
        ]
        full_events = [
            event for event in game_state_events if event.get("subtype") == "full"
        ]
        diff_events = [
            event for event in game_state_events if event.get("subtype") == "diff"
        ]

        self.assertEqual(len(game_state_events), 328)
        self.assertEqual(len(full_events), 1)
        self.assertEqual(len(diff_events), 327)

    def test_parse_yields_exact_match_state_transitions(self):
        parser = MTGALogParser(SAMPLE_LOG)
        parser.entity_resolver = StubEntityResolver()

        match_events = [
            event
            for event in parser.parse()
            if event.get("type") == "match_state"
            and event.get("state") in {"Playing", "MatchCompleted"}
        ]

        self.assertEqual(
            match_events,
            [
                {
                    "type": "match_state",
                    "old": "ConnectedToMatchDoor_ConnectingToGRE",
                    "new": "Playing",
                    "state": "Playing",
                },
                {
                    "type": "match_state",
                    "old": "Playing",
                    "new": "MatchCompleted",
                    "state": "MatchCompleted",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
