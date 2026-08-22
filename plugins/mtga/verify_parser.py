"""Verification script for MTGA log parser against docs/log-single-game.log."""

import collections

from plugins.mtga.parser import MTGALogParser


EXPECTED = {
    "payloads": 271,
    "client_messages": 542,
    "game_states": 328,
    "full_states": 1,
    "diff_states": 327,
    "match_states": ["Playing", "MatchCompleted"],
    "annotations": 845,
    "phase_step_annotations": 141,
    "new_turn_annotations": 13,
    "zone_transfer_annotations": 57,
    "damage_annotations": 40,
    "turn_event_count": 13,
    "final_phase": "Combat",
    "final_step": "CombatDamage",
    "game_objects": 171,
    "zones": 17,
    "zone_references": 198,
    "missing_zone_references": 99,
    "zone_mismatches": 0,
    "duplicate_zone_memberships": 0,
}


class StubEntityResolver:
    def resolve_card(self, grp_id: int) -> dict:
        return {
            "grpId": grp_id,
            "name": f"Card({grp_id})",
            "type": "Unknown",
            "colors": [],
            "source": "stub",
        }


def zone_reference_stats(parser: MTGALogParser) -> dict:
    references = []
    missing = []
    mismatches = []

    for zone_id, zone in parser.game_state["zones"].items():
        for object_id in zone.get("objectInstanceIds", []):
            references.append((zone_id, object_id))
            obj = parser.game_state["game_objects"].get(object_id)
            if obj is None:
                missing.append((zone_id, object_id))
            elif obj.get("zoneId") != zone_id:
                mismatches.append((zone_id, object_id, obj.get("zoneId")))

    reference_counts = collections.Counter(object_id for _, object_id in references)
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


def main() -> None:
    log_path = "docs/log-single-game.log"
    print(f"Parsing {log_path}...")

    raw_parser = MTGALogParser(log_path)
    payload_count = sum(1 for _ in raw_parser.iter_gre_payloads())

    raw_parser = MTGALogParser(log_path)
    messages = list(raw_parser.iter_gre_client_messages())
    game_state_messages = [
        message["gameStateMessage"]
        for message in messages
        if "gameStateMessage" in message
    ]
    full_state_count = sum(
        1
        for message in game_state_messages
        if message.get("type") == "GameStateType_Full"
    )
    diff_state_count = sum(
        1
        for message in game_state_messages
        if message.get("type") == "GameStateType_Diff"
    )

    parser = MTGALogParser(log_path)
    parser.entity_resolver = StubEntityResolver()
    parsed_events = list(parser.parse())
    annotation_counts = collections.Counter(
        annotation_type
        for event in parser.events
        for annotation_type in event["types"]
    )
    zone_stats = zone_reference_stats(parser)
    match_states = [
        event["state"]
        for event in parsed_events
        if event.get("type") == "match_state"
        and event.get("state") in {"Playing", "MatchCompleted"}
    ]

    actual = {
        "payloads": payload_count,
        "client_messages": len(messages),
        "game_states": len(game_state_messages),
        "full_states": full_state_count,
        "diff_states": diff_state_count,
        "match_states": match_states,
        "annotations": len(parser.events),
        "phase_step_annotations": annotation_counts["PhaseOrStepModified"],
        "new_turn_annotations": annotation_counts["NewTurnStarted"],
        "zone_transfer_annotations": annotation_counts["ZoneTransfer"],
        "damage_annotations": annotation_counts["DamageDealt"],
        "turn_event_count": parser.game_state["turn_info"]["turn_event_count"],
        "final_phase": parser.game_state["turn_info"]["phase_name"],
        "final_step": parser.game_state["turn_info"]["step_name"],
        "game_objects": len(parser.game_state["game_objects"]),
        "zones": len(parser.game_state["zones"]),
        "zone_references": len(zone_stats["references"]),
        "missing_zone_references": len(zone_stats["missing"]),
        "zone_mismatches": len(zone_stats["mismatches"]),
        "duplicate_zone_memberships": len(zone_stats["duplicates"]),
    }

    print("\n--- MTGA Parser Verification Results ---")
    for key, expected_value in EXPECTED.items():
        actual_value = actual[key]
        status = "OK" if actual_value == expected_value else "FAIL"
        print(f"{key}: {actual_value} expected {expected_value} [{status}]")

    failures = [
        key
        for key, expected_value in EXPECTED.items()
        if actual[key] != expected_value
    ]
    if failures:
        raise SystemExit(f"Verification failed: {', '.join(failures)}")

    print("Verification completed successfully.")


if __name__ == "__main__":
    main()
