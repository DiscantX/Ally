"""Pure color conversion functions for ANSI and hex color formats.
"""
import re
import hashlib


def color_for_key(key: str, palette: list[str]) -> str:
    """Deterministic, stable across process restarts -- do NOT use Python's
    built-in hash() here, it's salted per-process (PYTHONHASHSEED) and
    will assign a different color to the same key every run.
    """
    if not palette:
        return "#ffffff"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(palette)
    return palette[index]


def hex_to_ansi_fg(hex_color: str) -> str:
    """Converts a '#rrggbb' hex string to a 24-bit ANSI foreground SGR
    code body, e.g. '#ff2ddc' -> '38;2;255;45;220'. Does not include the
    leading '\\033[' or trailing 'm' -- callers wrap it themselves, matching
    the existing convention in infrastructure/logger/logger.py's COLORS dict.
    """
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"38;2;{r};{g};{b}"


def ansi_fg_to_hex(ansi_code: str) -> str:
    """Converts an ANSI foreground SGR code body back to '#rrggbb' hex.
    Supports two input shapes:
      - 24-bit: '38;2;R;G;B'
      - xterm-256 indexed: '38;5;N' (both the 6x6x6 cube range 16-231
        and the grayscale ramp range 232-255; raise ValueError for N < 16,
        since that range is terminal-theme-dependent with no single
        correct RGB value -- do not silently guess).
    Raises ValueError on any other/malformed input rather than guessing.
    """
    # Check for 24-bit RGB SGR
    m24 = re.search(r'38;2;(\d+);(\d+);(\d+)', ansi_code)
    if m24:
        r, g, b = map(int, m24.groups())
        for val in (r, g, b):
            if not (0 <= val <= 255):
                raise ValueError(f"RGB values out of range: {r}, {g}, {b}")
        return f"#{r:02x}{g:02x}{b:02x}"

    # Check for xterm-256 indexed SGR
    m256 = re.search(r'38;5;(\d+)', ansi_code)
    if m256:
        n = int(m256.group(1))
        if n < 16:
            raise ValueError(f"xterm-256 color index {n} < 16 is terminal-theme-dependent.")
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
        else:
            raise ValueError(f"Invalid xterm-256 color index: {n}")

    # Fallbacks for basic named colors if needed, or raise ValueError
    basic_map = {
        "31": "#ff0000",
        "32": "#00ff00",
        "33": "#ffff00",
        "34": "#0000ff",
        "37": "#ffffff",
        "1;91": "#ff5555",
        "1;92": "#55ff55",
        "1;93": "#ffff55",
        "1;94": "#5555ff",
        "1;95": "#ff55ff",
        "1;96": "#55ffff",
        "1;97": "#ffffff",
        "0": "#ffffff",
    }
    cleaned = ansi_code.strip()
    if cleaned in basic_map:
        return basic_map[cleaned]

    raise ValueError(f"Unsupported or malformed ANSI code format: {ansi_code}")
