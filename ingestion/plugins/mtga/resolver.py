"""MTGA Entity and Enum Resolver (SQLite Backend).

Resolves entity grpIds against local MTGA SQLite card database files
(Raw_CardDatabase_<hash>.mtga and Raw_ClientLocalization_<hash>.mtga) and provides
enum resolutions for phases, steps, zones, and colors.
"""

import glob
import os
import sqlite3
from typing import Any, Dict, List, Optional
import os


class BaseLookupResolver:
    """Base class for MTGA local SQLite database file lookups and caching."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
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

    def __init__(self, data_dir: Optional[str] = None) -> None:
        super().__init__(data_dir)
        self.cards_db: Dict[int, Dict[str, Any]] = {}
        self.loc_db: Dict[int, str] = {}
        self._loaded = False

    def load_data(self) -> bool:
        if self._loaded:
            return True

        if not os.path.isdir(self.data_dir):
            return False

        db_files = glob.glob(os.path.join(self.data_dir, "Raw_CardDatabase_*.mtga"))
        db_files += glob.glob(os.path.join(self.data_dir, "Raw_CardDatabase_*.db"))
        if not db_files:
            return False

        db_files.sort(key=os.path.getmtime, reverse=True)

        for db_file in db_files:
            conn = None
            try:
                conn = sqlite3.connect(db_file)
                conn.row_factory = sqlite3.Row
                self._load_localizations(conn)
                self._load_cards(conn)
            except sqlite3.DatabaseError:
                continue
            finally:
                if conn is not None:
                    conn.close()

        self._loaded = len(self.cards_db) > 0 or len(self.loc_db) > 0
        return self._loaded

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        cursor = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        return cursor.fetchone() is not None

    def _load_localizations(self, conn: sqlite3.Connection) -> None:
        if not self._table_exists(conn, "Localizations_enUS"):
            return

        cursor = conn.execute(
            "SELECT LocId, Loc FROM Localizations_enUS WHERE Loc IS NOT NULL"
        )
        for row in cursor:
            try:
                loc_id = int(row["LocId"])
            except (TypeError, ValueError):
                continue
            if loc_id not in self.loc_db:
                self.loc_db[loc_id] = str(row["Loc"])

    def _load_cards(self, conn: sqlite3.Connection) -> None:
        if not self._table_exists(conn, "Cards"):
            return

        cursor = conn.execute("SELECT * FROM Cards")
        for row in cursor:
            row_dict = dict(row)
            try:
                grp_id = int(row_dict["GrpId"])
            except (KeyError, TypeError, ValueError):
                continue
            if grp_id not in self.cards_db:
                self.cards_db[grp_id] = row_dict

    def resolve_card(self, grp_id: int, name_loc_id: Optional[int] = None) -> Dict[str, Any]:
        """Resolve a grpId to card metadata. If grpId isn't in the local
        Cards table -- the common case for dynamically-generated tokens,
        which often never get a permanent catalog entry -- fall back to
        resolving `name_loc_id` (the gameObject's own `name` field, a
        LocId) directly against the already-loaded localization table.
        This recovers the display name for free (no extra lookup source)
        but can't recover type/colors, since those live on the Cards row
        we don't have."""
        self.load_data()

        card_info = self.cards_db.get(int(grp_id))
        if not card_info:
            if name_loc_id is not None:
                fallback_name = self.loc_db.get(int(name_loc_id))
                if fallback_name:
                    return {
                        "grpId": grp_id, "name": fallback_name, "type": "Unknown",
                        "colors": [], "source": "token_name_fallback",
                    }
            return {
                "grpId": grp_id, "name": f"Card({grp_id})", "type": "Unknown",
                "colors": [], "source": "unresolved",
            }

        title_id = self._optional_int(card_info.get("TitleId"))
        type_id = self._optional_int(card_info.get("TypeTextId"))
        name = self.loc_db.get(title_id, f"Card({grp_id})") if title_id is not None else f"Card({grp_id})"
        card_type = self.loc_db.get(type_id, "Unknown") if type_id is not None else "Unknown"
        colors = self._resolve_colors(card_info.get("Colors"))

        return {
            "grpId": grp_id, "name": name, "type": card_type,
            "colors": colors, "source": "arena_db", "raw": card_info,
        }

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _resolve_colors(self, raw_colors: Any) -> List[str]:
        if raw_colors is None or raw_colors == "":
            return []
        if isinstance(raw_colors, int):
            color_ids = [raw_colors]
        elif isinstance(raw_colors, str):
            color_ids = [
                color_id.strip()
                for color_id in raw_colors.split(",")
                if color_id.strip()
            ]
        elif isinstance(raw_colors, list):
            color_ids = raw_colors
        else:
            return []

        colors = []
        for color_id in color_ids:
            parsed_color = self._optional_int(color_id)
            if parsed_color is not None:
                colors.append(EnumResolver.resolve_color(parsed_color))
            else:
                colors.append(str(color_id))
        return colors
