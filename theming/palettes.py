"""Color palettes and resolution logic for modules and log levels.
"""
from typing import Final
from interfaces.gui_qt.theming.palette_hash import color_for_key


THEME_MODULE_COLORS: Final[dict[str, dict[str, str]]] = {
    "Slate": {
        "SuperiorColliculus": "#00f0f0",
        "Inspect Coords": "#00ff00",
        "ScreenCollector": "#0000ff",
        "WindowManager": "#5f87af",
        "ConfigManager": "#5555ff",
        "Scribe": "#ffff00",
        "Ally": "#55ffff",
        "MemoryManager": "#ff55ff",
        "Main": "#ff2ddc",
        "Layout": "#87ffaf",
        "GeminiProvider": "#ffd700",
        "MemoryDB": "#55ff55",
        "UpdateDocs": "#ff0000",
        "AllyCore": "#af87d7",
        "ScreenClassifier": "#87ffaf",
        "ScreenBootstrapper": "#ff8787",
        "LayoutOCRReader": "#008787",
        "OCR": "#878700",
        "ClipClassifier": "#d7d7d7",
        "CategoryStore": "#af87d7",
        "EntityRegistry": "#87d7d7",
        "NarrativeMemory": "#ff87af",
        "PersonalityMemory": "#af00d7",
        "SaveTracker": "#444444",
        "Run": "#55ffff",
        "HeaderSplash": "#ff8700",
        "ProdOverlay": "#00f0f0",
        "SpeechRecognizer": "#01bbca",
        "UtteranceAssembler": "#cd24ba",
        "General": "#ffffff",
    },
}

THEME_MODULE_PALETTE_HUES: Final[dict[str, list[str]]] = {
    "Signal": [
        "#00ffcc", "#39ff88", "#ffd166", "#ff6f59",
        "#c77dff", "#4cc9f0", "#f72585", "#94ff5c",
        "#ff9f1c", "#7bdcff", "#e0aaff", "#ff5d8f",
    ],
    "Synthwave": [
        "#ff71ce", "#b967ff", "#01cdfe", "#05ffa1",
        "#fffb96", "#ff9e00", "#f15bb5", "#9b5de5",
        "#00bbf9", "#fee440", "#ff6392", "#72ddf7",
    ],
}

THEME_LEVEL_COLORS: Final[dict[str, dict[str, str]]] = {
    "Slate": {
        "debug": "#6a6a6a", "info": "#d4d4d4", "warning": "#dcdcaa",
        "error": "#f44747", "critical": "#f44747",
    },
    "Signal": {
        "debug": "#5c6773", "info": "#e0e0e0", "warning": "#ffd166",
        "error": "#ff4d6d", "critical": "#ff1744",
    },
    "Synthwave": {
        "debug": "#7a7599", "info": "#e6e6f5", "warning": "#fee440",
        "error": "#ff5277", "critical": "#ff0844",
    },
}


def resolve_module_color(theme_name: str, module_display_name: str) -> str:
    """Resolves the hex color for a module's display name under the given
    theme, applying fallback: exact match in THEME_MODULE_COLORS[theme_name]
    if present, else hashed hue from THEME_MODULE_PALETTE_HUES[theme_name]
    if present, else exact match in THEME_MODULE_COLORS["Slate"], else a
    neutral default ('#ffffff' -- matches palette_hash.color_for_key's own
    empty-palette fallback).
    """
    if theme_name in THEME_MODULE_COLORS and module_display_name in THEME_MODULE_COLORS[theme_name]:
        return THEME_MODULE_COLORS[theme_name][module_display_name]
    if theme_name in THEME_MODULE_PALETTE_HUES:
        palette = THEME_MODULE_PALETTE_HUES[theme_name]
        return color_for_key(module_display_name, palette)
    if "Slate" in THEME_MODULE_COLORS and module_display_name in THEME_MODULE_COLORS["Slate"]:
        return THEME_MODULE_COLORS["Slate"][module_display_name]
    return "#ffffff"
