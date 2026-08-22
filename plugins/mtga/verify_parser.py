"""Verification script for MTGA log parser against docs/log-single-game.log."""

from plugins.mtga.parser import MTGALogParser


EXPECTED = {
    "payloads": 271,
    "client_messages": 542,
    "game_states": 328,
    "full_states": 1,
    "diff_states": 327,
    "match_states": ["Playing", "MatchCompleted"],
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
