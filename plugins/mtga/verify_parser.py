"""Verification script for MTGA log parser against docs/log-single-game.log."""

import json
from plugins.mtga.parser import MTGALogParser


def main() -> None:
    log_path = "docs/log-single-game.log"
    print(f"Parsing {log_path}...")
    
    parser = MTGALogParser(log_path)
    
    event_count = 0
    full_state_count = 0
    diff_state_count = 0
    room_state_count = 0
    
    for event in parser.parse():
        event_count += 1
        e_type = event.get("type")
        if e_type == "game_state":
            sub = event.get("subtype")
            if sub == "full":
                full_state_count += 1
                if full_state_count == 1:
                    print("\n--- Sample Full Game State ---")
                    print(json.dumps(event.get("state"), indent=2)[:1000] + "\n... (truncated)")
            elif sub == "diff":
                diff_state_count += 1
                if diff_state_count == 1:
                    print("\n--- Sample Diff Game State ---")
                    print(json.dumps(event.get("state"), indent=2)[:1000] + "\n... (truncated)")
        elif e_type == "room_state":
            room_state_count += 1

    print("\n--- MTGA Parser Verification Results ---")
    print(f"Total events processed: {event_count}")
    print(f"Full Game States: {full_state_count}")
    print(f"Diff Game States: {diff_state_count}")
    print(f"Room State Events: {room_state_count}")
    print(f"Total Annotations captured: {len(parser.events)}")
    print(f"Final Turn Info: {parser.game_state.get('turn_info')}")
    print("\n--- Resolved Zones & Contents ---")
    print(json.dumps(parser.get_resolved_zones(), indent=2))
    print("Verification completed successfully.")


if __name__ == "__main__":
    main()
