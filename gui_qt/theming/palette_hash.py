"""Deterministic color assignment from a color palette using hashlib.md5.
"""
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
