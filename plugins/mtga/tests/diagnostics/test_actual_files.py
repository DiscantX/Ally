"""Diagnostic script to test MTGA entity resolution against the user's actual local installation files."""

import os
from plugins.mtga.resolver import EntityResolver


def main() -> None:
    print("Initializing EntityResolver...")
    resolver = EntityResolver()
    print(f"Resolved data directory: {resolver.data_dir}")
    print(f"Data directory exists: {os.path.isdir(resolver.data_dir)}")

    if os.path.isdir(resolver.data_dir):
        files = os.listdir(resolver.data_dir)
        print(f"Files in data directory ({len(files)} total):")
        for f in files[:20]:
            print(f"  - {f}")
    else:
        print("Warning: Data directory not found on this machine at default paths.")

    print("\nAttempting to load card and localization data...")
    loaded = resolver.load_data()
    print(f"Data loaded successfully: {loaded}")
    print(f"Loaded cards count: {len(resolver.cards_db)}")
    print(f"Loaded localization strings count: {len(resolver.loc_db)}")

    if resolver.cards_db:
        sample_grp_id = list(resolver.cards_db.keys())[0]
        resolved = resolver.resolve_card(sample_grp_id)
        print(f"\nSample card resolution (grpId={sample_grp_id}):")
        print(resolved)
    else:
        print("\nNo cards loaded from local files (falling back to built-in fallback catalog).")


if __name__ == "__main__":
    main()
