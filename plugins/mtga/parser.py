"""MTGA Log Parser and GameState Accumulator.

Parses MTGA Player.log messages, handles Full and Diff game state payloads,
extracts annotations (life changes, zone transfers, turn/phase changes),
and maintains a running game state accumulator.
"""

import json
from typing import Any, Dict, Generator, List, Optional, Tuple

from collectors.log_reader import LogReader


class MTGALogParser:
    """Parses MTGA log files and accumulates game state."""

    def __init__(self, log_path: str):
        self.log_path = log_path
        self.reader = LogReader(log_path, follow=False)
        self.game_state: Dict[str, Any] = {
            "players": {},
            "zones": {},
            "game_objects": {},
            "turn_info": {"turn": 0, "phase": 0, "step": 0},
            "match_state": "Unknown",
        }
        self.events: List[Dict[str, Any]] = []

    def parse(self) -> Generator[Dict[str, Any], None, None]:
        """Parse log file line by line, yielding parsed GRE messages and events."""
        prev_line = ""
        for line in self.reader.read_lines():
            # Check for match boundaries
            if "STATE CHANGED" in line:
                if "Playing" in line:
                    self.match_state = "Playing"
                    yield {"type": "match_state", "state": "Playing"}
                elif "MatchCompleted" in line:
                    self.match_state = "MatchCompleted"
                    yield {"type": "match_state", "state": "MatchCompleted"}

            # GRE Client Message framing: Header line followed by JSON payload starting with '{'
            if line.startswith("{") and ("GreToClientEvent" in prev_line or "GRE_to_Client" in prev_line or "GreToClient" in prev_line):
                try:
                    payload = json.loads(line)
                    parsed_event = self._handle_gre_message(payload)
                    if parsed_event:
                        yield parsed_event
                except json.JSONDecodeError:
                    pass

            prev_line = line

    def _handle_gre_message(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a parsed GRE-to-client event payload."""
        inner = payload.get("greToClientEvent", payload)
        
        messages = inner.get("greToClientMessages", [])
        if not messages and isinstance(inner, dict):
            messages = [inner]

        last_result = None
        for msg in messages:
            game_state_msg = msg.get("gameStateMessage") or inner.get("gameStateMessage")
            if game_state_msg:
                last_result = self._handle_game_state_message(game_state_msg)
            
            room_state = msg.get("matchGameRoomStateChangedEvent") or inner.get("matchGameRoomStateChangedEvent")
            if room_state:
                state_type = room_state.get("stateType")
                last_result = {"type": "room_state", "stateType": state_type}

        return last_result

    def _handle_game_state_message(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """Handle GameStateType_Full or GameStateType_Diff."""
        msg_type = msg.get("type")
        
        if msg_type == "GameStateType_Full" or msg_type == 1:
            self._apply_full_state(msg)
            return {"type": "game_state", "subtype": "full", "state": self.game_state}
        elif msg_type == "GameStateType_Diff" or msg_type == 2:
            events = self._apply_diff_state(msg)
            return {"type": "game_state", "subtype": "diff", "events": events, "state": self.game_state}

        return {"type": "game_state", "subtype": "unknown", "raw": msg}

    def _apply_full_state(self, msg: Dict[str, Any]) -> None:
        """Initialize full game state."""
        self.game_state = {
            "players": {},
            "zones": {},
            "game_objects": {},
            "turn_info": {"turn": 0, "phase": 0, "step": 0},
        }
        game_state = msg.get("gameState", msg)
        
        # Extract players, zones, objects if present
        players = game_state.get("players", [])
        for p in players:
            p_id = p.get("systemPlayerId") or p.get("playerId")
            if p_id:
                self.game_state["players"][p_id] = p

        zones = game_state.get("zones", [])
        for z in zones:
            z_id = z.get("zoneId")
            if z_id:
                self.game_state["zones"][z_id] = z

        objects = game_state.get("gameObjects", [])
        for obj in objects:
            obj_id = obj.get("instanceId") or obj.get("id")
            if obj_id:
                self.game_state["game_objects"][obj_id] = obj

    def _apply_diff_state(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Apply incremental diffs and extract semantic annotations."""
        diff_events = []
        diff = msg.get("diff", msg)
        
        # Update zones from diff
        zones = diff.get("zones", [])
        for z in zones:
            z_id = z.get("zoneId")
            if z_id:
                if z_id not in self.game_state["zones"]:
                    self.game_state["zones"][z_id] = {}
                self.game_state["zones"][z_id].update(z)

        # Update game objects from diff
        objects = diff.get("gameObjects", [])
        for obj in objects:
            obj_id = obj.get("instanceId") or obj.get("id")
            if obj_id:
                if obj_id not in self.game_state["game_objects"]:
                    self.game_state["game_objects"][obj_id] = {}
                self.game_state["game_objects"][obj_id].update(obj)

        annotations = diff.get("annotations", [])
        for ann in annotations:
            ann_types = ann.get("type", [])
            details = ann.get("details", [])
            
            # Helper to read typed detail values
            detail_dict = self._parse_details(details)
            
            event = {
                "types": ann_types,
                "affectorId": ann.get("affectorId"),
                "affectedIds": ann.get("affectedIds", []),
                "details": detail_dict,
            }
            diff_events.append(event)
            self.events.append(event)

            # Update running state based on annotation types
            if "NewTurnStarted" in ann_types or 48 in ann_types:
                turn_num = detail_dict.get("turn") or detail_dict.get("turnNumber")
                if turn_num is not None:
                    self.game_state["turn_info"]["turn"] = turn_num

            if "PhaseOrStepModified" in ann_types or 8 in ann_types:
                phase = detail_dict.get("phase")
                step = detail_dict.get("step")
                if phase is not None:
                    self.game_state["turn_info"]["phase"] = phase
                if step is not None:
                    self.game_state["turn_info"]["step"] = step

            if "ModifiedLife" in ann_types or 10 in ann_types:
                life_change = detail_dict.get("life") or detail_dict.get("value")
                # Could update player life totals here

        return diff_events

    def get_resolved_zones(self) -> Dict[str, List[Dict[str, Any]]]:
        """Resolve zone object instance IDs to actual game objects."""
        resolved = {}
        for z_id, zone in self.game_state["zones"].items.items() if hasattr(self.game_state["zones"].items, "items") else self.game_state["zones"].items(): # wait, dict items
            pass
        for z_id, zone in self.game_state["zones"].items():
            z_type = zone.get("type", "Unknown")
            instance_ids = zone.get("objectInstanceIds", [])
            objects = [self.game_state["game_objects"].get(i) for i in instance_ids if i in self.game_state["game_objects"]]
            resolved[str(z_id)] = {
                "type": z_type,
                "objects": [o for o in objects if o is not None]
            }
        return resolved

    def _parse_details(self, details: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract typed key-value pairs from annotation details."""
        parsed = {}
        for d in details:
            key = d.get("key")
            if not key:
                continue
            
            # Check value types
            val = None
            if "valueInt32" in d:
                v_list = d["valueInt32"]
                val = v_list[0] if isinstance(v_list, list) and v_list else v_list
            elif "valueUint32" in d:
                v_list = d["valueUint32"]
                val = v_list[0] if isinstance(v_list, list) and v_list else v_list
            elif "valueString" in d:
                v_list = d["valueString"]
                val = v_list[0] if isinstance(v_list, list) and v_list else v_list
            elif "valueBool" in d:
                v_list = d["valueBool"]
                val = v_list[0] if isinstance(v_list, list) and v_list else v_list
            elif "valueFloat" in d:
                v_list = d["valueFloat"]
                val = v_list[0] if isinstance(v_list, list) and v_list else v_list
            
            if val is not None:
                parsed[key] = val
        return parsed
