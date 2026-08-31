# Theming System Documentation

Ally's PySide6 graphical user interface uses a token-based theming architecture rendered via Qt Style Sheets (QSS) from Python templates. Because Qt Style Sheets do not support native CSS custom properties (`var()`), themes are defined as immutable dataclasses containing design tokens and rendered at startup.

## Design Tokens

Each [`Theme`](interfaces/gui_qt/theming/theme.py:14) instance defines the following token fields:

* `name`: Display name of the theme.
* `bg_base`: Primary background color for windows and base surfaces.
* `bg_surface`: Surface background color for panels, containers, and card areas.
* `bg_elevated`: Elevated background color for toolbars, inputs, and buttons.
* `fg_primary`: Primary text color for main body and titles.
* `fg_secondary`: Secondary text color for subtitles and secondary metadata.
* `fg_muted`: Muted text color for disabled items or subtle hints.
* `border`: Border color for framing components and dividers.
* `accent_primary`: Primary brand accent color for interactive highlights and focus elements.
* `accent_secondary`: Secondary accent color for gradients and alternate highlights.
* `success`: Semantic success color for confirmation indicators and positive states.
* `warning`: Semantic warning color for cautions and alerts.
* `error`: Semantic error color for dropped connections, failures, and critical errors.
* `focus_ring`: Focus indicator color for active input widgets.
* `companion_palette`: A list of 5–8 hex color strings used for deterministic personality and entity name-label coloring.

## Built-in Themes

### Signal

The default theme derived from legacy overlay configuration assets:

* `name`: `"Signal"`
* `bg_base`: `#1a1a1a`
* `bg_surface`: `#232323`
* `bg_elevated`: `#2d2d2d`
* `fg_primary`: `#e0e0e0`
* `fg_secondary`: `#aaaaaa`
* `fg_muted`: `#888888`
* `border`: `#333333`
* `accent_primary`: `#00ffcc`
* `accent_secondary`: `#00ffff`
* `success`: `#00cc77`
* `warning`: `#ff9900`
* `error`: `#c93b55`
* `focus_ring`: `#00ffcc`
* `companion_palette`: `["#ff9900", "#aa88ff", "#00cc77", "#c93b55", "#ffd966", "#00ffff", "#00ffcc"]`

### Synthwave

Derived from splash screen and gradient definitions:

* `name`: `"Synthwave"`
* `bg_base`: `#14101f`
* `bg_surface`: `#1e1830`
* `bg_elevated`: `#281f40`
* `fg_primary`: `#e6e6f5`
* `fg_secondary`: `#b8b3d1`
* `fg_muted`: `#7a7599`
* `border`: `#3a3355`
* `accent_primary`: `#00f0f0`
* `accent_secondary`: `#ff2ddc`
* `success`: `#00cc77`
* `warning`: `#ff9900`
* `error`: `#c93b55`
* `focus_ring`: `#00f0f0`
* `companion_palette`: `["#ff2ddc", "#cd24ba", "#9b1b98", "#00f0f0", "#01bcca", "#0289a5"]`

### NeutralContent

Dedicated to developer inspector content areas (JSON viewers, logs, tables) to ensure high-contrast readability resembling IDE editors:

* `name`: `"NeutralContent"`
* `bg_base`: `#1e1e1e`
* `bg_surface`: `#252526`
* `bg_elevated`: `#2d2d2d`
* `fg_primary`: `#d4d4d4`
* `fg_secondary`: `#9d9d9d`
* `fg_muted`: `#6a6a6a`
* `border`: `#3c3c3c`
* `accent_primary`: `#569cd6`
* `accent_secondary`: `#4ec9b0`
* `success`: `#6a9955`
* `warning`: `#dcdcaa`
* `error`: `#f44747`
* `focus_ring`: `#569cd6`
* `companion_palette`: `["#569cd6", "#4ec9b0", "#c586c0", "#ce9178", "#dcdcaa", "#9cdcfe"]`

## Object-Naming Conventions

Every widget in the PySide6 UI is assigned a structured `objectName` following a double-underscore parent/child convention:

```python
widget.setObjectName("feedPanel__scrollArea")
```

Examples include:

* `feedPanel`, `feedPanel__scrollArea`
* `messageRow`, `messageRow__nameLabel`, `messageRow__bodyLabel`
* `inputBar`, `inputBar__textEdit`, `inputBar__sendButton`, `inputBar__modeToggle`
* `statusStrip`, `statusStrip__connectionDot`, `statusStrip__personalityBadge`
* `devDock__visionPanel`, `devDock__ocrPanel`, `devDock__scribePanel`, `devDock__allyPanel`

## Dynamic Properties

Semantic states are applied via Qt dynamic properties rather than fixed widget IDs, allowing QSS rules to select on state dynamically:

* `speaker`: Set to `"ally"`, `"player"`, or `"system"` on message rows.
* `level`: Set to `"debug"`, `"info"`, `"warning"`, `"error"`, or `"critical"` on log-line widgets.

Widgets using dynamic properties require a style refresh after modification:

```python
widget.setProperty("speaker", "ally")
widget.style().unpolish(widget)
widget.style().polish(widget)
```

## Custom QSS Overrides

Advanced users and third-party theme authors can override generated stylesheets entirely without code changes:

1. Create a custom `.qss` stylesheet file on disk.
2. Configure its path in `user_config.json`:

```json
{
    "custom_qss_path": "path/to/my_custom_theme.qss"
}
```

When `custom_qss_path` is present and readable, `build_stylesheet()` loads its raw content as the active stylesheet instead of rendering [`base.qss.tmpl`](interfaces/gui_qt/theming/base.qss.tmpl).
