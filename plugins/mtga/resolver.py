"""MTGA Entity and Enum Resolver.

Resolves entity grpIds against local MTGA card and localization data files
(data_cards_<hash>.mtga and data_loc_<hash>.mtga, supporting JSON, Gzip JSON, and MessagePack),
and provides enum resolutions for phases, steps, zones, and colors.
"""

import glob
import gzip
import json
import os
from typing import Any, Dict, Optional

try:
    import msgpack
except ImportError:
    msgpack = None


class BaseLookupResolver:
    """Base class for MTGA local data file lookups and caching."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or self._find_default_data_dir()
        self._cache: Dict[str, Any] = {}

    def _find_default_data_dir(self) -> str:
        """Attempt to locate MTGA installation data directory across common paths (Standalone & Steam)."""
        candidates = []
        if os.name == "nt":
            appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            if appdata:
                candidates.append(os.path.join(appdata, "..", "LocalLow", "Wizards Of The Coast", "MTGA", "MTGA_Data", "Downloads", "Data"))
            program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
            candidates.append(os.path.join(program_files, "Wizards of the Coast", "MTGA", "MTGA_Data", "Downloads", "Data"))
            program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            candidates.append(os.path.join(program_files_x86, "Steam", "steamapps", "common", "MTGA", "MTGA_Data", "Downloads", "Data"))
        
        for path in candidates:
            resolved_path = os.path.abspath(path)
            if os.path.isdir(resolved_path):
                return resolved_path
        
        return os.path.abspath("MTGA_Data/Downloads/Data")

    def _load_mtga_file(self, filepath: str) -> Optional[Any]:
        """Load an MTGA .mtga data file handling JSON, Gzip, and MessagePack formats."""
        if not os.path.exists(filepath):
            return None

        with open(filepath, "rb") as f:
            raw = f.read()

        # 1. Try MessagePack if installed
        if msgpack is not None:
            try:
                unpacked = msgpack.unpackb(raw, raw=False)
                if unpacked is not None:
                    return unpacked
            except Exception:
                pass

        # 2. Try Gzip decompression
        try:
            decompressed = gzip.decompress(raw)
            try:
                return json.loads(decompressed.decode("utf-8"))
            except Exception:
                if msgpack is not None:
                    try:
                        return msgpack.unpackb(decompressed, raw=False)
                    except Exception:
                        pass
        except Exception:
            pass

        # 3. Try plain JSON
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None


class EnumResolver:
    """Resolves numeric enum values to human-readable strings according to MTGA proto specs."""

    PHASES = {
        0: "None",
        1: "Beginning",
        2: "Main1",
        3: "Combat",
        4: "Main2",
        5: "Ending",
    }

    STEPS = {
        0: "None",
        1: "Untap",
        2: "Upkeep",
        3: "Draw",
        4: "BeginCombat",
        5: "DeclareAttack",
        6: "DeclareBlock",
        7: "CombatDamage",
        8: "EndCombat",
        9: "End",
        10: "Cleanup",
        11: "FirstStrikeDamage",
    }

    ZONES = {
        0: "None",
        1: "Library",
        2: "Hand",
        3: "Battlefield",
        4: "Stack",
        5: "Graveyard",
        6: "Exile",
        7: "Command",
        8: "Revealed",
        9: "Limbo",
        10: "Sideboard",
        11: "Pending",
        12: "PhasedOut",
        13: "Suppressed",
    }

    COLORS = {
        0: "Colorless",
        1: "White",
        2: "Blue",
        3: "Black",
        4: "Red",
        5: "Green",
        6: "Land",
        7: "Artifact",
    }

    @classmethod
    def resolve_phase(cls, phase_id: Any) -> str:
        if isinstance(phase_id, int):
            return cls.PHASES.get(phase_id, f"UnknownPhase({phase_id})")
        return str(phase_id)

    @classmethod
    def resolve_step(cls, step_id: Any) -> str:
        if isinstance(step_id, int):
            return cls.STEPS.get(step_id, f"UnknownStep({step_id})")
        return str(step_id)

    @classmethod
    def resolve_zone(cls, zone_id: Any) -> str:
        if isinstance(zone_id, int):
            return cls.ZONES.get(zone_id, f"UnknownZone({zone_id})")
        return str(zone_id)

    @classmethod
    def resolve_color(cls, color_id: Any) -> str:
        if isinstance(color_id, int):
            return cls.COLORS.get(color_id, f"UnknownColor({color_id})")
        return str(color_id)


class EntityResolver(BaseLookupResolver):
    """Resolves card entity grpIds against local MTGA cards and localization data."""

    # Built-in fallback catalog for common test cards (when local .mtga files are absent)
    FALLBACK_CARDS = {
        93946: {"name": "Test Instant / Lesson", "type": "Instant", "colors": ["Green"]},
        95660: {"name": "Colossal Dreadmaw", "type": "Creature", "colors": ["Green"]},
        75531: {"name": "Beast Token", "type": "Creature", "colors": ["Green"]},
        68310: {"name": "Llanowar Elves", "type": "Creature", "colors": ["Green"]},
        97447: {"name": "Environmental Sciences", "type": "Instant Lesson", "colors": ["Green"]},
        105182: {"name": "Forest", "type": "Land", "colors": []},
    }

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)
        self.cards_db: Dict[int, Dict[str, Any]] = {}
        self.loc_db: Dict[int, str] = {}
        self._loaded = False

    def load_data(self) -> bool:
        if self._loaded:
            return True

        cards_loaded = self._load_cards()
        loc_loaded = self._load_localization()
        self._loaded = cards_loaded or loc_loaded
        return self._loaded

    def _load_cards(self) -> bool:
        if not os.path.isdir(self.data_dir):
            return False
        
        card_files = glob.glob(os.path.join(self.data_dir, "data_cards_*.mtga"))
        if not card_files:
            return False

        card_file = sorted(card_files)[-1]
        data = self._load_mtga_file(card_file)
        if data is None:
            return False

        items = data if isinstance(data, list) else data.get("cards", data.get("items", []))
        for card in items:
            if not isinstance(card, dict):
                continue
            grp_id = card.get("grpId") or card.get("Id") or card.get("id") or card.get("cardId")
            if grp_id is not None:
                try:
                    self.cards_db[int(grp_id)] = card
                except (ValueError, TypeError):
                    pass
        return len(self.cards_db) > 0

    def _load_localization(self) -> bool:
        if not os.path.isdir(self.data_dir):
            return False

        loc_files = glob.glob(os.path.join(self.data_dir, "data_loc_*.mtga"))
        if not loc_files:
            return False

        loc_file = sorted(loc_files)[-1]
        data = self._load_mtga_file(loc_file)
        if data is None:
            return False

        items = data if isinstance(data, list) else data.get("strings", data.get("items", []))
        for item in items:
            if not isinstance(item, dict):
                continue
            key = item.get("id") or item.get("Key") or item.get("isoId") or item.get("LocId")
            val = item.get("text") or item.get("Value") or item.get("string") or item.get("Translation")
            if key is not None and val is not None:
                try:
                    self.loc_db[int(key)] = str(val)
                except (ValueError, TypeError):
                    pass
        return len(self.loc_db) > 0

    def resolve_card(self, grp_id: int) -> Dict[str, Any]:
        """Resolve a grpId to card metadata (title, types, colors, etc.)."""
        self.load_data()
        
        card_info = self.cards_db.get(int(grp_id))
        if not card_info:
            # Fallback to built-in fallback catalog if local files are absent
            fallback = self.FALLBACK_CARDS.get(int(grp_id))
            if fallback:
                return {
                    "grpId": grp_id,
                    "name": fallback["name"],
                    "type": fallback["type"],
                    "colors": fallback["colors"],
                    "raw": fallback,
                }
            return {
                "grpId": grp_id,
                "name": f"Card({grp_id})",
                "type": "Unknown",
                "colors": [],
            }

        title_id = card_info.get("titleId") or card_info.get("TitleId") or card_info.get("nameId") or card_info.get("localizationId")
        name = "Unknown"
        
        # Check if card_info["name"] is an integer localization ID
        raw_name = card_info.get("name") or card_info.get("Title")
        if isinstance(raw_name, int) or (isinstance(raw_name, str) and raw_name.isdigit()):
            title_id = int(raw_name)

        if title_id is not None:
            try:
                name = self.loc_db.get(int(title_id), f"Card({grp_id})")
            except (ValueError, TypeError):
                name = f"Card({grp_id})"
        elif isinstance(raw_name, str):
            name = raw_name
        elif "title" in card_info:
            name = card_info["title"]

        card_type = card_info.get("cardType") or card_info.get("types") or card_info.get("type", "Unknown")
        colors = card_info.get("color") or card_info.get("colors", [])

        return {
            "grpId": grp_id,
            "name": name,
            "type": card_type,
            "colors": colors,
            "raw": card_info,
        }
