#!/usr/bin/env python3
"""
Diagnostic script to convert xterm-256 indices in infrastructure/logger/logger.py
to 24-bit RGB hex values, cross-checking index 208, 128, and 121 against published charts.
"""

import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.logger.logger import COLORS


def xterm256_to_hex(ansi_code_body: str) -> str:
    """
    Converts xterm-256 ansi code body (e.g. '38;5;208' or '1;38;5;214') to hex '#rrggbb'.
    """
    parts = ansi_code_body.split(";")
    if "5" in parts:
        idx_5 = parts.index("5")
        if idx_5 + 1 < len(parts):
            n = int(parts[idx_5 + 1])
        else:
            raise ValueError(f"Malformed xterm code: {ansi_code_body}")
    else:
        raise ValueError(f"Not an xterm-256 indexed code: {ansi_code_body}")

    if 16 <= n <= 231:
        i = n - 16
        r_idx = i // 36
        g_idx = (i % 36) // 6
        b_idx = i % 6
        r = 0 if r_idx == 0 else 55 + 40 * r_idx
        g = 0 if g_idx == 0 else 55 + 40 * g_idx
        b = 0 if b_idx == 0 else 55 + 40 * b_idx
        return f"#{r:02x}{g:02x}{b:02x}"
    elif 232 <= n <= 255:
        v = 8 + 10 * (n - 232)
        return f"#{v:02x}{v:02x}{v:02x}"
    elif 0 <= n <= 15:
        raise ValueError(f"Legacy 16-color index {n} encountered - terminal dependent.")
    else:
        raise ValueError(f"Invalid xterm-256 index {n}")


def main():
    print("=" * 70)
    print("XTERM-256 TO HEX CONVERSION DIAGNOSTIC")
    print("=" * 70)

    # Published chart cross-checks (Index 128 computed formula yields #af00d7)
    expected_cross_checks = {
        208: "#ff8700",  # orange
        128: "#af00d7",  # purple
        121: "#87ffaf",  # mint
    }

    discrepancies = []
    converted_palette = {}

    print(f"{'Color Name':<15} | {'ANSI Code':<15} | {'Computed Hex':<12} | {'Status'}")
    print("-" * 70)

    for name, code in COLORS.items():
        if "38;5;" in code:
            try:
                hex_val = xterm256_to_hex(code)
                converted_palette[name] = hex_val
                
                match_status = "OK"
                for c_idx, exp_hex in expected_cross_checks.items():
                    if f";{c_idx}" in code or code.endswith(str(c_idx)):
                        if hex_val.lower() != exp_hex.lower():
                            match_status = f"MISMATCH (Exp: {exp_hex})"
                            discrepancies.append((name, c_idx, hex_val, exp_hex))
                        else:
                            match_status = f"Verified Index {c_idx}"

                print(f"{name:<15} | {code:<15} | {hex_val:<12} | {match_status}")
            except Exception as e:
                print(f"{name:<15} | {code:<15} | {'ERROR':<12} | {e}")
                discrepancies.append((name, code, str(e)))

    print("=" * 70)
    if discrepancies:
        print(f"[FAIL] BAIL-OUT CONDITION MET: {len(discrepancies)} discrepancy/discrepancies found!")
        for d in discrepancies:
            print(f"  - {d}")
        sys.exit(1)
    else:
        print("[SUCCESS] All xterm-256 indexed colors successfully converted and cross-checked against published charts!")
        print("Verified cross-checks:")
        print("  - Index 208 (orange) -> #ff8700")
        print("  - Index 128 (purple) -> #af00d7")
        print("  - Index 121 (mint)   -> #87ffaf")
        sys.exit(0)


if __name__ == "__main__":
    main()
