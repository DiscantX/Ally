"""Theme dataclass and built-in themes (SIGNAL, SYNTHWAVE, SLATE)
plus QSS stylesheet generation with support for custom_qss_path overrides.
"""
from dataclasses import dataclass, field
import os
import json
from typing import Optional
from infrastructure.logger import log
from theming.palettes import THEME_MODULE_COLORS, THEME_LEVEL_COLORS


@dataclass(frozen=True)
class Theme:
    name: str
    bg_base: str
    bg_surface: str
    bg_elevated: str
    fg_primary: str
    fg_secondary: str
    fg_muted: str
    border: str
    accent_primary: str
    accent_secondary: str
    success: str
    warning: str
    error: str
    focus_ring: str
    companion_palette: list[str] = field(default_factory=list)
    font_mono: str = '"Cascadia Code", "Consolas", "JetBrains Mono", monospace'
    module_log_colors: dict[str, str] = field(default_factory=dict)
    log_level_colors: dict[str, str] = field(default_factory=dict)


SIGNAL = Theme(
    name="Signal",
    bg_base="#1a1a1a",
    bg_surface="#232323",
    bg_elevated="#2d2d2d",
    fg_primary="#e0e0e0",
    fg_secondary="#aaaaaa",
    fg_muted="#888888",
    border="#333333",
    accent_primary="#00ffcc",
    accent_secondary="#00ffff",
    success="#00cc77",
    warning="#ff9900",
    error="#c93b55",
    focus_ring="#00ffcc",
    companion_palette=["#ff9900", "#aa88ff", "#00cc77", "#c93b55", "#ffd966", "#00ffff", "#00ffcc"],
    font_mono='"Cascadia Code", "Consolas", "JetBrains Mono", monospace',
    module_log_colors=THEME_MODULE_COLORS.get("Signal", {}),
    log_level_colors=THEME_LEVEL_COLORS["Signal"],
)

SYNTHWAVE = Theme(
    name="Synthwave",
    bg_base="#14101f",
    bg_surface="#1e1830",
    bg_elevated="#281f40",
    fg_primary="#e6e6f5",
    fg_secondary="#b8b3d1",
    fg_muted="#7a7599",
    border="#3a3355",
    accent_primary="#00f0f0",
    accent_secondary="#ff2ddc",
    success="#00cc77",
    warning="#ff9900",
    error="#c93b55",
    focus_ring="#00f0f0",
    companion_palette=["#ff2ddc", "#cd24ba", "#9b1b98", "#00f0f0", "#01bcca", "#0289a5"],
    font_mono='"Cascadia Code", "Consolas", "JetBrains Mono", monospace',
    module_log_colors=THEME_MODULE_COLORS.get("Synthwave", {}),
    log_level_colors=THEME_LEVEL_COLORS["Synthwave"],
)

SLATE = Theme(
    name="Slate",
    bg_base="#1e1e1e",
    bg_surface="#252526",
    bg_elevated="#2d2d2d",
    fg_primary="#d4d4d4",
    fg_secondary="#9d9d9d",
    fg_muted="#6a6a6a",
    border="#3c3c3c",
    accent_primary="#569cd6",
    accent_secondary="#4ec9b0",
    success="#6a9955",
    warning="#dcdcaa",
    error="#f44747",
    focus_ring="#569cd6",
    companion_palette=["#569cd6", "#4ec9b0", "#c586c0", "#ce9178", "#dcdcaa", "#9cdcfe"],
    font_mono='"Cascadia Code", "Consolas", "JetBrains Mono", monospace',
    module_log_colors=THEME_MODULE_COLORS.get("Slate", {}),
    log_level_colors=THEME_LEVEL_COLORS["Slate"],
)

# Deprecated compatibility alias for NEUTRAL_CONTENT_THEME
NEUTRAL_CONTENT_THEME = SLATE


def build_stylesheet(theme: Theme, template_path: str, dev_font_scale: float = 1.0) -> str:
    """Loads a QSS template and formats it with theme token values and font scaling.
    Also checks user_config.json for a custom_qss_path override.
    """
    custom_path: Optional[str] = None
    try:
        user_config_path = "user_config.json"
        if os.path.exists(user_config_path):
            with open(user_config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                custom_path = cfg.get("custom_qss_path")
    except Exception as e:
        log("Failed to load user_config.json for custom QSS override: {e}", e=e, level="warning")

    if custom_path and os.path.exists(custom_path):
        try:
            with open(custom_path, "r", encoding="utf-8") as f:
                log("Loading custom QSS override from {path}", path=custom_path)
                return f.read()
        except Exception as e:
            log("Failed to read custom QSS override from {path}: {e}", path=custom_path, e=e, level="warning")

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
        ctx = dict(theme.__dict__)
        ctx["dev_font_size"] = f"{11.0 * dev_font_scale:.1f}pt"
        ctx["dev_font_size_11"] = f"{11.0 * dev_font_scale:.1f}pt"
        ctx["dev_font_size_10"] = f"{10.0 * dev_font_scale:.1f}pt"
        return template.format(**ctx)
    except Exception as e:
        log("Failed to build stylesheet from template {path}: {e}", path=template_path, e=e, level="error")
        return ""


TEMPLATE_PATH: str = os.path.join(os.path.dirname(__file__), "base.qss.tmpl")
