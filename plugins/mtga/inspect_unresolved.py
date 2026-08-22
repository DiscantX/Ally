"""Diagnostic (not a unittest): dumps everything we actually know about
each object that failed name resolution, plus an independent, direct
SQLite check against the real Cards table -- bypassing EntityResolver
entirely -- so we're not just re-confirming a bug in our own loading
code with more of our own loading code.

Usage:
    python plugins/mtga/inspect_unresolved.py [path/to/Player.log]
"""

import glob
import os
import sqlite3
import sys

from plugins.mtga.parser import MTGALogParser
from plugins.mtga.resolver import EntityResolver


def independent_lookup(data_dir: str, grp_ids: set[int]) -> dict[int, dict | None]:
    """Raw sqlite3 query against Cards, with zero shared code path with
    EntityResolver. If this disagrees with EntityResolver's verdict for
    the same grpId, the bug is in our loading code, not in Arena's data."""
    results: dict[int, dict | None] = {gid: None for gid in grp_ids}
    db_files = glob.glob(os.path.join(data_dir, "Raw_CardDatabase_*.mtga"))
    db_files += glob.glob(os.path.join(data_dir, "Raw_CardDatabase_*.db"))
    for db_file in db_files:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        try:
            placeholders = ",".join("?" * len(grp_ids))
            cursor = conn.execute(
                f"SELECT * FROM Cards WHERE GrpId IN ({placeholders})", list(grp_ids)
            )
            for row in cursor:
                results[int(row["GrpId"])] = dict(row)
        except sqlite3.DatabaseError:
            pass
        finally:
            conn.close()
    return results


def main() -> None:
    log_path = sys.argv[1] if len(sys.argv) > 1 else "docs/log-single-game.log"
    resolver = EntityResolver()
    parser = MTGALogParser(log_path)
    parser.entity_resolver = resolver
    list(parser.parse())

    unresolved = {}
    for obj_id, obj in parser.game_state["game_objects"].items():
        card = obj.get("resolved_card")
        if card is not None and card["source"] == "unresolved":
            unresolved[obj_id] = obj

    if not unresolved:
        print("Nothing unresolved -- token fallback likely closed the gap already.")
        return

    print(f"{len(unresolved)} objects still genuinely unresolved:\n")
    grp_ids = set()
    for obj_id, obj in unresolved.items():
        grp_id = obj.get("grpId")
        grp_ids.add(grp_id)
        print(f"--- object {obj_id} ---")
        print(f"  grpId:        {grp_id}")
        print(f"  name (LocId): {obj.get('name')}")
        print(f"  zoneId:       {obj.get('zoneId')}")
        print(f"  ownerSeatId:  {obj.get('ownerSeatId')}")
        print(f"  controllerSeatId: {obj.get('controllerSeatId')}")
        print(f"  visibility:   {obj.get('visibility')}")
        type_fields = {k: v for k, v in obj.items() if "type" in k.lower()}
        print(f"  type-ish fields (name -> value): {type_fields}")
        print(f"  objectSourceGrpId: {obj.get('objectSourceGrpId')}")
        print(f"  parentId:          {obj.get('parentId')}")
        print(f"  ALL raw keys: {sorted(obj.keys())}")
        print()

    resolver.load_data()
    print(f"\nIndependent direct-SQLite check against {resolver.data_dir}:")
    direct = independent_lookup(resolver.data_dir, grp_ids)
    for grp_id, row in direct.items():
        status = "FOUND in Cards table" if row else "genuinely absent from Cards table"
        print(f"  grpId {grp_id}: {status}")
        if row:
            print(f"    -> our resolver MISSED an existing row: {row}")


if __name__ == "__main__":
    main()