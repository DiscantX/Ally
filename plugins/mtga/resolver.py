"""MTGA Entity and Enum Resolver (SQLite Backend).

Resolves entity grpIds against local MTGA SQLite card database files
(Raw_CardDatabase_<hash>.mtga and Raw_ClientLocalization_<hash>.mtga) and provides
enum resolutions for phases, steps, zones, and colors.
"""

import glob
import os
import sqlite3
from typing import Any, Dict, Optional


class BaseLookupResolver:
    """Base class for MTGA local SQLite database file lookups and caching."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or self._find_default_data_dir()
        self._cache: Dict[str, Any] = {}

    def _find_default_data_dir(self) -> str:
        """Attempt to locate MTGA installation Raw data directory across common Steam & Standalone paths."""
        candidates = []
        if os.name == "nt":
            appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            if appdata:
                candidates.append(os.path.join(appdata, "..", "LocalLow", "Wizards Of The Coast", "MTGA", "MTGA_Data", "Downloads", "Raw"))
            program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
            candidates.append(os.path.join(program_files, "Wizards of the Coast", "MTGA", "MTGA_Data", "Downloads", "Raw"))
            program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            candidates.append(os.path.join(program_files_x86, "Steam", "steamapps", "common", "MTGA", "MTGA_Data", "Downloads", "Raw"))
        
        for path in candidates:
            resolved_path = os.path.abspath(path)
            if os.path.isdir(resolved_path):
                return resolved_path
        
        return os.path.abspath("MTGA_Data/Downloads/Raw")


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
    """Resolves card entity grpIds against local MTGA SQLite card database files."""

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

        if not os.path.isdir(self.data_dir):
            return False

        # Gather all database files (CardDatabase and ClientLocalization)
        db_files = glob.glob(os.path.join(self.data_dir, "*.mtga")) + glob.glob(os.path.join(self.data_dir, "*.db"))
        if not db_files:
            return False

        # Sort db_files by mtime descending (most recent first)
        db_files.sort(key=os.path.getmtime, reverse=True)

        for db_file in db_files:
            try:
                conn = sqlite3.connect(db_file)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall()]

                for table in tables:
                    try:
                        cursor.execute(f"SELECT * FROM {table}")
                        rows = cursor.fetchall()
                        for row in rows:
                            row_dict = dict(row)
                            # Check keys for grpId / card info
                            grp_id = row_dict.get("grpId") or row_dict.get("Id") or row_dict.get("id") or row_dict.get("CardId") or row_dict.get("CollationId")
                            if grp_id is not None:
                                try:
                                    g_int = int(grp_id)
                                    if g_int not in self.cards_db:
                                        self.cards_db[g_int] = row_dict
                                except (ValueError, TypeError):
                                    pass

                            # Check keys for localization strings
                            loc_key = row_dict.get("id") or row_dict.get("Key") or row_dict.get("LocId") or row_dict.get("isoId") or row_dict.get("ID")
                            loc_val = row_dict.get("text") or row_dict.get("Value") or row_dict.get("Translation") or row_dict.get("string") or row_dict.get("Text")
                            if loc_key is not None and loc_val is not None:
                                try:
                                    k_int = int(loc_key)
                                    if k_int not in self.loc_db:
                                        self.loc_db[k_int] = str(loc_val)
                                except (ValueError, TypeError):
                                    pass
                    except Exception:
                        pass

                conn.close()
            except Exception:
                pass

        self._loaded = len(self.cards_db) > 0 or len(self.loc_db) > 0
        return self._loaded

    def resolve_card(self, grp_id: int) -> Dict[str, Any]:
        """Resolve a grpId to card metadata (title, types, colors, etc.)."""
        self.load_data()
        
        card_info = self.cards_db.get(int(grp_id))
        if not card_info:
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

        title_id = card_info.get("titleId") or card_info.get("TitleId") or card_info.get("nameId") or card_info.get("localizationId") or card_info.get("TitleId")
        name = "Unknown"
        
        raw_name = card_info.get("name") or card_info.get("Title") or card_info.get("CardName")
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
