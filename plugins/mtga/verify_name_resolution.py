"""Diagnostic (not a unittest): runs the parser with the *real* EntityResolver
against a real captured log and reports how well name resolution actually
worked end-to-end -- not just in isolation against the resolver's own tests.

Usage:
    python plugins/mtga/verify_name_resolution.py [path/to/Player.log]

Defaults to docs/log-single-game.log if no path given.
"""

import sys
import collections

from plugins.mtga.parser import MTGALogParser


def main() -> None:
    log_path = sys.argv[1] if len(sys.argv) > 1 else "docs/log-single-game.log"
    print(f"Parsing {log_path} with the real EntityResolver (no stub)...")

    parser = MTGALogParser(log_path)  # default entity_resolver is the real one
    list(parser.parse())

    objects = parser.game_state["game_objects"]
    resolved, unresolved = [], []
    for obj_id, obj in objects.items():
        card = obj.get("resolved_card")
        if card is None:
            continue  # object never carried a grpId at all (rare, but possible)
        if card["source"] == "arena_db":
            resolved.append(card)
        else:
            unresolved.append((obj_id, obj.get("grpId"), card))

    total = len(resolved) + len(unresolved)
    rate = (len(resolved) / total * 100) if total else 0.0

    print(f"\n{len(resolved)}/{total} objects resolved to real card data ({rate:.1f}%)")

    type_breakdown = collections.Counter(
        obj.get("type", "(no type field)") for obj in objects.values()
    )
    print("\nBreakdown by gameObject 'type' (across ALL objects, resolved or not):")
    for obj_type, count in type_breakdown.most_common():
        print(f"  {obj_type}: {count}")

    if unresolved:
        print(f"\n{len(unresolved)} UNRESOLVED (grpId not found in local Arena DB):")
        for obj_id, grp_id, card in unresolved[:15]:
            print(f"  - object {obj_id}: grpId={grp_id} -> fell back to '{card['name']}'")
        if len(unresolved) > 15:
            print(f"  ... and {len(unresolved) - 15} more")

    print("\nSample of resolved names (first 15, deduped by name):")
    seen = set()
    shown = 0
    for card in resolved:
        if card["name"] in seen:
            continue
        seen.add(card["name"])
        print(f"  - {card['name']} ({card['type']}, colors={card['colors']})")
        shown += 1
        if shown >= 15:
            break

    if rate < 90.0 and total > 0:
        print(
            "\n[WARN] Resolution rate under 90% -- worth checking whether this "
            "log predates your current local card DB snapshot, or whether some "
            "grpIds belong to token/emblem types not in the Cards table."
        )


if __name__ == "__main__":
    main()