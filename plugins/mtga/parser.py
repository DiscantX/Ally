"""MTGA Log Parser and GameState Accumulator.

Parses MTGA Player.log messages, handles Full and Diff game state payloads,
extracts annotations (life changes, zone transfers, turn/phase changes),
and maintains a running game state accumulator with entity and enum resolution.
"""

import json
from typing import Any, Dict, Generator, List, Optional

from collectors.log_reader import LogReader
from plugins.mtga.resolver import EntityResolver, EnumResolver


class MTGALogParser:
    """Parses MTGA log files and accumulates game state with card and enum resolution."""

    ANNOTATION_TYPES = {
        1: "ZoneTransfer",
        3: "DamageDealt",
        4: "TappedUntappedPermanent",
        8: "PhaseOrStepModified",
        10: "ModifiedLife",
        13: "ObjectIdChanged",
        34: "ManaPaid",
        35: "TokenCreated",
        43: "ResolutionStart",
        44: "ResolutionComplete",
        48: "NewTurnStarted",
    }

    def __init__(self, log_path: str):
        self.log_path = log_path
        self.reader = LogReader(log_path, follow=False)
        self.entity_resolver = EntityResolver()
        self.enum_resolver = EnumResolver()
        self.game_state: Dict[str, Any] = {
            "players": {},
            "zones": {},
            "game_objects": {},
            "turn_info": {
                "turn": 0,
                "turn_event_count": 0,
                "phase": 0,
                "phase_name": "None",
                "step": 0,
                "step_name": "None",
            },
            "match_state": "Unknown",
        }
        self.match_state = "Unknown"
        self.events: List[Dict[str, Any]] = []

    def iter_gre_payloads(self) -> Generator[Dict[str, Any], None, None]:
        """Yield framed GRE JSON payloads from the log without interpreting them."""
        prev_line = ""
        for line in self.reader.read_lines():
            if line.startswith("{") and self._is_gre_header(prev_line):
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass
            prev_line = line

    def iter_gre_client_messages(self) -> Generator[Dict[str, Any], None, None]:
        """Yield each individual greToClientMessages item from framed GRE payloads."""
        for payload in self.iter_gre_payloads():
            inner = payload.get("greToClientEvent", payload)
            messages = inner.get("greToClientMessages", [])
            if messages:
                yield from messages
            elif isinstance(inner, dict):
                yield inner

    def parse(self) -> Generator[Dict[str, Any], None, None]:
        """Parse log file line by line, yielding parsed GRE messages and events."""
        prev_line = ""
        for line in self.reader.read_lines():
            if "STATE CHANGED" in line:
                state_event = self._parse_state_changed(line)
                if state_event:
                    self.match_state = state_event["new"]
                    self.game_state["match_state"] = self.match_state
                    yield {
                        "type": "match_state",
                        "old": state_event["old"],
                        "new": state_event["new"],
                        "state": state_event["new"],
                    }

            # GRE Client Message framing: Header line followed by JSON payload starting with '{'
            if line.startswith("{") and self._is_gre_header(prev_line):
                try:
                    payload = json.loads(line)
                    for parsed_event in self._handle_gre_payload(payload):
                        yield parsed_event
                except json.JSONDecodeError:
                    pass

            prev_line = line

    @staticmethod
    def _is_gre_header(line: str) -> bool:
        return "GreToClientEvent" in line or "GRE_to_Client" in line or "GreToClient" in line

    @staticmethod
    def _parse_state_changed(line: str) -> Optional[Dict[str, str]]:
        marker = "STATE CHANGED"
        if marker not in line:
            return None

        _, _, raw_json = line.partition(marker)
        raw_json = raw_json.strip()
        try:
            state = json.loads(raw_json)
        except json.JSONDecodeError:
            return None

        old = state.get("old")
        new = state.get("new")
        if not isinstance(old, str) or not isinstance(new, str):
            return None
        return {"old": old, "new": new}

    def _handle_gre_payload(self, payload: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        """Process a parsed GRE-to-client event payload."""
        inner = payload.get("greToClientEvent", payload)
        
        messages = inner.get("greToClientMessages", [])
        if not messages and isinstance(inner, dict):
            messages = [inner]

        for msg in messages:
            game_state_msg = msg.get("gameStateMessage")
            if game_state_msg:
                yield self._handle_game_state_message(game_state_msg)
            
            room_state = msg.get("matchGameRoomStateChangedEvent")
            if room_state:
                state_type = room_state.get("stateType")
                yield {"type": "room_state", "stateType": state_type}

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
            "turn_info": {
                "turn": 0,
                "turn_event_count": 0,
                "phase": 0,
                "phase_name": "None",
                "step": 0,
                "step_name": "None",
            },
            "match_state": self.match_state,
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
                z_type_val = z.get("type")
                if z_type_val is not None:
                    z["type_name"] = self.enum_resolver.resolve_zone(z_type_val)
                self.game_state["zones"][z_id] = z

        objects = game_state.get("gameObjects", [])
        for obj in objects:
            obj_id = obj.get("instanceId") or obj.get("id")
            if obj_id:
                grp_id = obj.get("grpId")
                if grp_id is not None:
                    obj["resolved_card"] = self.entity_resolver.resolve_card(int(grp_id))
                self.game_state["game_objects"][obj_id] = obj
                self._reconcile_object_zone(obj_id)

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
                z_type_val = z.get("type")
                if z_type_val is not None:
                    z["type_name"] = self.enum_resolver.resolve_zone(z_type_val)
                self.game_state["zones"][z_id].update(z)

        # Update game objects from diff
        objects = diff.get("gameObjects", [])
        for obj in objects:
            obj_id = obj.get("instanceId") or obj.get("id")
            if obj_id:
                if obj_id not in self.game_state["game_objects"]:
                    self.game_state["game_objects"][obj_id] = {}
                grp_id = obj.get("grpId")
                if grp_id is not None:
                    obj["resolved_card"] = self.entity_resolver.resolve_card(int(grp_id))
                self.game_state["game_objects"][obj_id].update(obj)
                self._reconcile_object_zone(obj_id)

        annotations = diff.get("annotations", [])
        for ann in annotations:
            raw_ann_types = ann.get("type", [])
            ann_types = self._normalize_annotation_types(raw_ann_types)
            details = ann.get("details", [])
            
            # Helper to read typed detail values
            detail_dict = self._parse_details(details)
            
            event = {
                "types": ann_types,
                "raw_types": raw_ann_types,
                "affectorId": ann.get("affectorId"),
                "affectedIds": ann.get("affectedIds", []),
                "details": detail_dict,
            }
            diff_events.append(event)
            self.events.append(event)

            # Update running state based on annotation types
            if self._has_annotation_type(ann_types, "NewTurnStarted"):
                self.game_state["turn_info"]["turn_event_count"] += 1
                turn_num = detail_dict.get("turn") or detail_dict.get("turnNumber")
                if turn_num is not None:
                    self.game_state["turn_info"]["turn"] = turn_num

            if self._has_annotation_type(ann_types, "ObjectIdChanged"):
                old_id = detail_dict.get("orig_id")
                new_id = detail_dict.get("new_id")
                if old_id is not None:
                    self._remove_object_from_zones(old_id)
                if new_id is not None:
                    self._reconcile_object_zone(new_id)

            if self._has_annotation_type(ann_types, "PhaseOrStepModified"):
                phase = detail_dict.get("phase")
                step = detail_dict.get("step")
                if phase is not None:
                    self.game_state["turn_info"]["phase"] = phase
                    self.game_state["turn_info"]["phase_name"] = self.enum_resolver.resolve_phase(phase)
                if step is not None:
                    self.game_state["turn_info"]["step"] = step
                    self.game_state["turn_info"]["step_name"] = self.enum_resolver.resolve_step(step)

        return diff_events

    @classmethod
    def _normalize_annotation_type(cls, ann_type: Any) -> str:
        if isinstance(ann_type, int):
            return cls.ANNOTATION_TYPES.get(ann_type, f"UnknownAnnotation({ann_type})")
        if isinstance(ann_type, str):
            prefix = "AnnotationType_"
            if ann_type.startswith(prefix):
                return ann_type[len(prefix):]
            return ann_type
        return str(ann_type)

    @classmethod
    def _normalize_annotation_types(cls, ann_types: Any) -> List[str]:
        if not isinstance(ann_types, list):
            ann_types = [ann_types]
        return [cls._normalize_annotation_type(ann_type) for ann_type in ann_types]

    @staticmethod
    def _has_annotation_type(ann_types: List[str], expected: str) -> bool:
        return expected in ann_types

    def _remove_object_from_zones(self, object_id: int) -> None:
        for zone in self.game_state["zones"].values():
            instance_ids = zone.get("objectInstanceIds")
            if not isinstance(instance_ids, list):
                continue
            zone["objectInstanceIds"] = [
                existing_id
                for existing_id in instance_ids
                if existing_id != object_id
            ]

    def _reconcile_object_zone(self, object_id: int) -> None:
        obj = self.game_state["game_objects"].get(object_id)
        if not obj:
            return

        zone_id = obj.get("zoneId")
        if zone_id is None:
            return

        self._remove_object_from_zones(object_id)
        zone = self.game_state["zones"].get(zone_id)
        if zone is None:
            return

        instance_ids = zone.setdefault("objectInstanceIds", [])
        if isinstance(instance_ids, list) and object_id not in instance_ids:
            instance_ids.append(object_id)

    def get_resolved_zones(self) -> Dict[str, List[Dict[str, Any]]]:
        """Resolve zone object instance IDs to actual game objects."""
        resolved = {}
        for z_id, zone in self.game_state["zones"].items():
            z_type = zone.get("type", "Unknown")
            z_type_name = zone.get("type_name") or self.enum_resolver.resolve_zone(z_type)
            instance_ids = zone.get("objectInstanceIds", [])
            objects = [self.game_state["game_objects"].get(i) for i in instance_ids if i in self.game_state["game_objects"]]
            resolved[str(z_id)] = {
                "type": z_type,
                "type_name": z_type_name,
                "objects": [o for o in objects if o is not None]
            }
        return resolved

    def _parse_details(self, details: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract typed key-value pairs from annotation details."""
        parsed = {}
        if not details:
            return parsed
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
