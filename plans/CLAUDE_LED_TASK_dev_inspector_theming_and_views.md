# Task: Dev Inspector Theming Foundation + JSON Tree Views + OCR Panel Redesign

## Context (read before starting)

The dev inspector (`interfaces/gui_qt/dev/`) was deliberately left unstyled
early on — every panel hardcodes its own inline `setStyleSheet(...)` call
against `NEUTRAL_CONTENT_THEME`, and there is no theme switching. This was a
mistake: text is hard to read, and there's no reason a dev tool can't be as
themeable as an IDE. This task fixes that, and also upgrades two panels
(Scribe/Ally JSON viewers, OCR panel) that are currently barely usable.

This task does **not** cover the Timing Waterfall — that's
`CLAUDE_LED_TASK_dev_inspector_timing_waterfall.md`, a separate task.

**This task has 5 phases. Please subdivide into sub-tasks along these phase
boundaries** — each phase has its own verification gate and should be
completed and verified before starting the next, since later phases build on
data structures Phase 0/1 introduce.

**Follow CLAUDE.md and `.markdownlint.yaml` conventions throughout**
(type hints, no `# type: ignore`, dataclasses over dicts, logger
`MODULE_NAME`/`REGISTRY` pattern, additive-over-modificatory).

---

## Phase 0 — Verification gates (mandatory, do this first)

Per project convention, do not write integration code against an assumption
you haven't verified live. Two independent things need verifying here.

### 0.1 — xterm-256 → hex conversion, verified programmatically

`infrastructure/logger/logger.py`'s `COLORS` dict contains some entries that
are true 24-bit RGB ANSI codes (e.g. `"magenta": "38;2;255;45;220"`) and some
that are legacy xterm-256 index codes (e.g. `"orange": "38;5;208"`,
`"purple": "38;5;128"`, `"mint": "38;5;121"`, `"teal": "38;5;30"`, `"olive":
"38;5;100"`, `"sky_blue": "38;5;117"`, `"steel_blue": "38;5;67"`,
`"dark_grey": "38;5;238"`, `"salmon": "38;5;210"`, `"pink": "38;5;211"`,
`"lavender": "38;5;141"`, `"violet": "38;5;177"`, `"lime": "38;5;118"`,
`"gold": "38;5;220"`).

Write a small standalone script (`tooling/tools/debug_xterm256_conversion.py`
or similar — diagnostic only, not part of the production path) that:

1. Implements the standard xterm-256 index → RGB formula for the two ranges
   that appear in this table:
   - Indices 16–231 (6×6×6 color cube): for index `n` in this range, let
     `i = n - 16`; `r_idx = i // 36`, `g_idx = (i % 36) // 6`, `b_idx = i % 6`;
     each channel value is `0` if its index is `0`, else `55 + 40 * index`.
   - Indices 232–255 (grayscale ramp): `v = 8 + 10 * (n - 232)` for all three
     channels.
   - (Indices 0–15 do not appear in this table's `38;5;N` codes — no need to
     implement the legacy 16-color table unless you find one; if you do find
     a `38;5;N` code with `N < 16` anywhere, stop and flag it rather than
     guessing, since that range has terminal-theme-dependent values with no
     single correct RGB.)
2. Runs this formula against every `38;5;N` entry in `COLORS` and prints a
   table of `name -> ansi_code -> computed_hex`.
3. Cross-checks at least 3 of the computed hex values against a reputable
   published xterm-256 color chart (e.g. search "xterm 256 color chart hex"
   and compare index 208, 128, and 121 by hand) and includes those
   cross-checks as comments in the diagnostic script's output/docstring.

**Bail-out condition:** if any computed value doesn't match a published
chart, stop before Phase 1 and report the discrepancy — do not proceed with
an unverified conversion baked into `Slate`'s palette.

Once verified, this diagnostic script's output becomes the literal hex
values used in Phase 1's `Slate` palette (§1.3 below) — copy them from the
verified output, not from a fresh manual calculation.

### 0.2 — Qt QSS selector mechanism, verified live

Qt's QSS engine does not reliably support CSS3 attribute-prefix selectors
(`[objectName^="devDock__"]`) the way browser CSS does — Qt's selector
support is closer to CSS 2.1 and is exact-match-oriented. Before restructuring
every panel's styling around a selector strategy, verify which one actually
works in this project's installed PySide6 version (`pyside6==6.11.1` per
`requirements.txt`).

Write a tiny standalone throwaway Qt script (delete when done, or keep under
`tooling/tools/` as a diagnostic if you prefer) that creates a `QApplication`,
a couple of `QWidget`s, and tests, in order:

1. `widget.setProperty("themed", "devPanel")` + a QSS rule
   `QWidget[themed="devPanel"] { background-color: red; }` — confirm this
   renders red. (This is the primary candidate — dynamic properties are
   Qt's documented, reliable way to do this.)
2. As a secondary check only if (1) fails: `objectName` attribute-prefix
   selectors (`QWidget[objectName^="devDock__"]`) — confirm whether this
   renders correctly or silently matches nothing.

**Decision rule:** if (1) works (expected), use the dynamic-property
approach for all of Phase 1's QSS centralization. If (1) unexpectedly fails
too, **stop and report back** rather than falling through to a third
approach on your own — this would mean re-scoping Phase 1 to per-widget
`setStyleSheet()` calls built from a shared helper function instead of pure
QSS, which is a large enough scope change to need a sign-off before
continuing.

---

## Phase 1 — `theming/` package, `Slate` theme, logger rewire, dev-inspector Theme menu, QSS centralization

### 1.1 — New top-level `theming/` package (sibling to `infrastructure/`, `interfaces/`, `utils/` — NOT nested under either)

This package holds pure data and pure functions only. **No PySide6 import
anywhere in this package, ever.** It exists so that both
`infrastructure/logger/logger.py` and `interfaces/gui_qt/theming/theme.py`
can depend on the same palette data without either domain depending on the
other — the same relationship `utils/event_hook.py` already has with the
rest of the codebase (a shared primitive, not owned by either side).

Create:

```text
theming/
    __init__.py
    color_convert.py
    palettes.py
```

**`theming/color_convert.py`** — pure functions, full type hints, no
external dependencies beyond the standard library:

```python
def hex_to_ansi_fg(hex_color: str) -> str:
    """Converts a '#rrggbb' hex string to a 24-bit ANSI foreground SGR
    code body, e.g. '#ff2ddc' -> '38;2;255;45;220'. Does not include the
    leading '\\033[' or trailing 'm' -- callers wrap it themselves, matching
    the existing convention in infrastructure/logger/logger.py's COLORS dict.
    """

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
```

Use regex to parse the SGR code body (split on `;`, inspect the second
field to distinguish `2` (24-bit) from `5` (indexed)). Add unit tests
(`tests/test_color_convert.py`) covering: a 24-bit round-trip, a 6x6x6-cube
index, a grayscale-ramp index, and the `N < 16` rejection case.

**`theming/palettes.py`** — the actual color data, keyed by theme name
(string keys `"Slate"`, `"Signal"`, `"Synthwave"` — matching `Theme.name`
exactly, since that's how consumers will look these up):

```python
from typing import Final

# Exact per-module hex colors. Only "Slate" has a hand-curated exact
# entry per module (see Phase 1.3) -- Signal and Synthwave intentionally
# do NOT get exact per-module entries; they resolve via
# THEME_MODULE_PALETTE_HUES instead (see below). A theme with no entry
# in this dict falls back to Slate's exact mapping.
THEME_MODULE_COLORS: Final[dict[str, dict[str, str]]] = {
    "Slate": {
        # populated in Phase 1.3, one entry per current REGISTRY module,
        # using the *display name* (REGISTRY[...]["name"], e.g. "Scribe",
        # "AllyCore", "SuperiorColliculus") as the key, not the filename.
    },
}

# Hashed-palette hues for themes that don't hand-curate an exact color
# per module. A module name is mapped deterministically onto one hue in
# this list via the same color_for_key() hash already used for
# companion_palette (interfaces/gui_qt/theming/palette_hash.py) --
# reused, not reimplemented.
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

# Log-level colors (debug/info/warning/error/critical), one set per theme.
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

# ANSI SGR bold/inverse cannot be expressed in a plain hex value. Themes
# that want "critical" rows to carry that extra visual weight in the GUI
# (not just a color swap) should still get it -- see Phase 1.5's QSS rule,
# which applies bold + a background tint to any row/line tagged level
# "critical" regardless of active theme. Do not try to encode this here.


def resolve_module_color(theme_name: str, module_display_name: str) -> str:
    """Resolves the hex color for a module's display name under the given
    theme, applying fallback: exact match in THEME_MODULE_COLORS[theme_name]
    if present, else hashed hue from THEME_MODULE_PALETTE_HUES[theme_name]
    if present, else exact match in THEME_MODULE_COLORS["Slate"], else a
    neutral default ('#ffffff' -- matches palette_hash.color_for_key's own
    empty-palette fallback).
    """
```

`resolve_module_color()` is the one function both consumers below call —
don't duplicate this fallback logic at each call site.

### 1.2 — `Theme` extended, `NEUTRAL_CONTENT_THEME` renamed to `SLATE`

In `interfaces/gui_qt/theming/theme.py`:

- Rename `NEUTRAL_CONTENT_THEME` to `SLATE` everywhere it's referenced
  across the codebase (search all usages — at minimum `THEMING.md`'s prose,
  every dev panel file's inline style references, and any other import).
  Keep `NEUTRAL_CONTENT_THEME` as a **deprecated alias** (`NEUTRAL_CONTENT_THEME
  = SLATE`) at the bottom of the module for one release, per the project's
  "additive over modificatory" convention — don't break any import you
  might have missed. Add a one-line comment noting it's a compatibility
  alias for the old name.
- Add three new fields to the `Theme` dataclass: `font_mono: str`,
  `module_log_colors: dict[str, str] = field(default_factory=dict)`,
  `log_level_colors: dict[str, str] = field(default_factory=dict)`.
- Set `font_mono='"Cascadia Code", "Consolas", "JetBrains Mono", monospace'`
  on all three theme instances (`SIGNAL`, `SYNTHWAVE`, `SLATE`) — same value
  for all three is fine, this isn't a per-theme aesthetic choice, it's a
  legibility baseline.
- Populate `module_log_colors` and `log_level_colors` on each theme instance
  by importing from `theming.palettes` at module load time:
  `module_log_colors=THEME_MODULE_COLORS.get(name, {})` (empty dict for
  Signal/Synthwave is correct and expected — they resolve via hashed hues
  instead, at lookup time via `resolve_module_color()`, not by pre-populating
  this field with computed values) and `log_level_colors=THEME_LEVEL_COLORS[name]`.

### 1.3 — `logger.py` rewired to consume `theming/`, `COLORS`/per-entry color removed

In `infrastructure/logger/logger.py`:

- **Delete** the `COLORS` dict entirely, and delete the `"color"` key from
  every entry in `REGISTRY` (keep the `"name"` key — that's still needed
  for the terminal display name and stays exactly as-is).
- Before deleting, **use Phase 0.1's verified diagnostic output** to write
  out `THEME_MODULE_COLORS["Slate"]` in `theming/palettes.py`, one entry
  per current `REGISTRY` module, keyed by that module's `"name"` value
  (e.g. `"Scribe": "#..."`, `"AllyCore": "#..."`), converting each old
  `COLORS[old_color_key]` value to hex via `hex_to_ansi_fg`'s inverse
  reasoning — i.e. for 24-bit entries, parse the `38;2;R;G;B` triple
  directly into `#rrggbb`; for `38;5;N` entries, use the Phase 0.1-verified
  computed hex. Also add `THEME_MODULE_COLORS["Slate"]["General"]` for the
  `DEFAULT_BRAIN` fallback case (`"#ffffff"`, matching today's `"white"`).
- `resolve_module_info()` and `log()` currently look up `COLORS.get(color_key,
  "37")` and build ANSI codes from it. Replace this with a call to
  `theming.palettes.resolve_module_color("Slate", brain_name)` (hardcode
  `"Slate"` for now — terminal theme switching is explicitly out of scope
  for this task, this hardcode is intentional and should have a short
  comment saying so, e.g. `# Terminal output is not theme-switchable yet;
  Slate is used as the terminal's fixed palette. See ally_decision_log.md.`),
  then `theming.color_convert.hex_to_ansi_fg(...)` to get back to an ANSI
  SGR body, then wrap it in `\033[{code}m` exactly as today.
- Level colors (`lvl_debug`, `lvl_info`, etc.) currently also come from
  `COLORS`. Resolve these the same way, via
  `theming.palettes.THEME_LEVEL_COLORS["Slate"][level.lower()]` →
  `hex_to_ansi_fg(...)`.
- **Verify no visual regression**: run the app (or a quick smoke test) and
  confirm terminal log output looks the same as before this change — same
  colors, same alignment. This refactor should be invisible in the terminal;
  only the *source* of the colors changed.

### 1.4 — Dev-inspector Theme menu + persistence

In `interfaces/gui_qt/dev/dev_window.py`:

- Add a **"Theme"** menu (alongside the existing "View" and "Layout" menus)
  with three checkable/radio-style actions: **Slate**, **Signal**,
  **Synthwave**. Use a `QActionGroup` so selection is mutually exclusive.
- `DevInspectorWindow` currently takes a `theme: Theme` constructor argument
  and applies it once via `build_stylesheet()` in `__init__`. Change this so
  the active theme is stored as `self._active_theme_name: str` (persisted
  separately from — and defaulting independently of — whatever theme the
  *overlay* is using; these must not be coupled, per the earlier design
  discussion: a player might run Synthwave overlay + Slate dev inspector,
  or any other combination).
- Persist the selected theme name via the existing
  `QSettings("Ally", "DevInspectorWindow")` store (same store already used
  for `geometry`/`adsState`) under a new key, e.g. `"devThemeName"`.
  **Default to `"Slate"`** on first run (no persisted value yet) — this is
  the fallback theme per the earlier design decision, not an arbitrary
  choice.
- Switching the Theme menu selection should call a new
  `_apply_active_theme()` method that: resolves the `Theme` instance by
  name (`{"Slate": SLATE, "Signal": SIGNAL, "Synthwave": SYNTHWAVE}[name]`),
  rebuilds/reapplies the stylesheet the same way `_apply_theme()` already
  does in `overlay_window.py`, and propagates the new theme to every panel
  that currently hardcodes `NEUTRAL_CONTENT_THEME`/`SLATE` inline (see 1.5 —
  this should mostly become automatic once panels stop hardcoding their own
  styles and instead pull from the dock manager's active theme).
- This method should also be called once at startup after restoring the
  persisted theme name, so panels render correctly on first show, not just
  on menu interaction.

### 1.5 — QSS centralization: remove inline per-panel styling

This is the biggest mechanical part of Phase 1. Currently these files each
call `setStyleSheet(f"background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; color:
{NEUTRAL_CONTENT_THEME.fg_primary}; ...")` inline, hardcoded to the old
`NEUTRAL_CONTENT_THEME` name specifically:

- `interfaces/gui_qt/dev/panels/timing_panel.py` (`_table`)
- `interfaces/gui_qt/dev/panels/ally_panel.py` (`_text`)
- `interfaces/gui_qt/dev/panels/ocr_panel.py` (`_text`) — being replaced
  in Phase 4 anyway, but still needs the class-level QSS hookup now
- `interfaces/gui_qt/dev/panels/entity_panel.py` (`_table`)
- `interfaces/gui_qt/dev/panels/scribe_panel.py` (`_text`)
- `interfaces/gui_qt/dev/panels/debug_panel.py` (`_image_label`)
- `interfaces/gui_qt/dev/panels/memory_panel.py` (`_summary_text`, `_log_text`)
- `interfaces/gui_qt/dev/panels/output_panel.py` (`_text`)
- `interfaces/gui_qt/dev/panels/vision_panel.py` (multiple: pipeline card
  frames, title labels, image labels, log tail)
- `interfaces/gui_qt/dev/panels/thinking_panel.py` (`_text`)

**Given Phase 0.2's verified mechanism**, the plan (assuming dynamic
properties work, which is expected):

1. On every themed content widget in the list above, replace the inline
   `setStyleSheet(...)` call with `widget.setProperty("themed", "<role>")`,
   where `<role>` is one of a small fixed vocabulary you define, e.g.
   `"devPanelText"` (read-only text/JSON views), `"devPanelTable"`
   (`QTableWidget`s), `"devPanelSurface"` (generic surface/background-only
   widgets like `debug_panel`'s image label), `"devPanelTitle"` (small
   accent-colored title labels like `vision_panel`'s per-card titles).
   Reuse the same 3-4 roles everywhere rather than inventing a new one per
   widget — the goal is a handful of reusable QSS rules, not one per widget.
2. After setting the property, call `widget.style().unpolish(widget);
   widget.style().polish(widget)` (same pattern `feed_panel.py` already
   uses for its `speaker` dynamic property) so the property takes effect
   immediately at construction time.
3. Add corresponding rules to `interfaces/gui_qt/theming/base.qss.tmpl`
   (or a new adjacent template file included alongside it — your call,
   but keep it in the same `theming/` folder as the existing template for
   discoverability) using the theme's format tokens, e.g.:

   ```qss
   QWidget[themed="devPanelText"] {{
       background-color: {bg_surface};
       color: {fg_primary};
       font-family: {font_mono};
       font-size: {dev_font_size}pt;
   }}
   QWidget[themed="devPanelTable"] {{
       background-color: {bg_surface};
       color: {fg_primary};
       gridline-color: {border};
       font-family: {font_mono};
       font-size: {dev_font_size}pt;
   }}
   ```

   Note the `{dev_font_size}` token — this doesn't exist on `Theme` yet and
   shouldn't (text size is a separate settings concern per Phase 2, not a
   theme property). `build_stylesheet()` (or a new
   `build_dev_stylesheet(theme, font_scale)` variant used only by the dev
   inspector) needs to compute this value and pass it into the `.format()`
   call alongside the theme's own `__dict__` fields. Coordinate this
   plumbing with Phase 2 rather than inventing a separate mechanism there.
4. Add a theme-independent QSS rule for critical-level log rows (bold +
   background tint) as flagged in `theming/palettes.py`'s comment (§1.1) —
   apply this via a `level` dynamic property already partially supported
   per `THEMING.md`'s existing "Dynamic Properties" section
   (`level: "debug"|"info"|"warning"|"error"|"critical"`), extending that
   existing convention to actually get wired up rather than just documented.
5. Remove the inline `setStyleSheet(...)` calls from each of the 10 files
   listed above once their QSS equivalents are confirmed working.

**If Phase 0.2 found that dynamic-property selectors don't work either**:
stop before doing this and report back — do not fall through to a third
approach unilaterally, per the bail-out condition stated in Phase 0.2.

### 1.6 — GUI log panels resolve module/level color via active theme, live-updating on theme switch

- `OutputPanel` and the embedded log tails in `MemoryPanel`/`VisionPanel`
  currently render plain-text lines (`f"[{entry.brain_name}] {entry.message}"`)
  with no per-module color at all in the GUI (only the terminal has this
  today). Change these to render as rich text (`QTextEdit.append()` already
  supports HTML — use `insertHtml()`/HTML-formatted `append()` calls instead
  of plain `append()`), coloring `[brain_name]` using
  `theming.palettes.resolve_module_color(active_theme_name, entry.brain_name)`
  and coloring the message body using
  `active_theme.log_level_colors.get(entry.level, active_theme.fg_primary)`.
- These panels need to know the *currently active dev-inspector theme name*
  (from `DevInspectorWindow._active_theme_name`, set in 1.4) — pass it in at
  construction, or better, give each of these panels a small
  `set_active_theme(theme_name: str)` method that `DevInspectorWindow.
  _apply_active_theme()` calls on every relevant panel when the theme
  changes, so switching themes recolors already-visible log history
  immediately rather than only affecting future lines. This likely means
  each panel needs to retain enough of its own log history to re-render
  (`OutputPanel` already keeps `_all_entries` for its channel filter —
  reuse that; `MemoryPanel`/`VisionPanel`'s tails are capped at 5 lines,
  so just re-render `_log_tail` on theme change, no new storage needed
  there).

### Phase 1 — verification / definition of done

- Terminal output is visually unchanged (colors, alignment) compared to
  before this task, confirmed by running the app.
- `theming/` package exists at the top level with no PySide6 import
  anywhere in it, has unit tests for `color_convert.py`.
- `NEUTRAL_CONTENT_THEME` is renamed to `SLATE` with a working deprecated
  alias; grep confirms no remaining references to the old name that
  bypass the alias unintentionally (the alias existing is fine; actively
  still typing the old name in new code is not).
- Dev inspector shows a working Theme menu; switching themes visibly
  changes panel backgrounds/text/borders across all 10 files in §1.5's
  list, and recolors log panel module-name/level coloring live.
- Theme selection persists across a close/reopen of the dev inspector.
- No panel file listed in §1.5 still contains an inline
  `setStyleSheet(f"...NEUTRAL_CONTENT_THEME...")` or
  `setStyleSheet(f"...SLATE...")` call.

---

## Phase 2 — Adjustable dev-inspector text size

- Add a **"View" menu → "Text Size"** submenu (or a new top-level "Text
  Size" menu, your call on which reads cleaner given the existing "View"
  menu's current contents) with radio actions: **Smallest, Small, Medium
  (default), Large, Largest**, plus a **"Custom…"** action that opens a
  small `QDialog` with a `QSpinBox` (reasonable bounds, e.g. 6–24 pt) for
  an exact point size.
- Represent the setting internally as a **scale multiplier**, not an
  absolute point size — e.g. `{"Smallest": 0.75, "Small": 0.85, "Medium":
  1.0, "Large": 1.2, "Largest": 1.4}` — applied against each QSS rule's
  base font size from §1.5 (so a `QTableWidget` rule's base 11px and a log
  tail's base 10px both scale together proportionally, preserving their
  existing relative sizing rather than forcing everything to one absolute
  size). "Custom…" should compute and store an equivalent scale multiplier
  relative to a fixed reference base size (use 11pt as the reference,
  matching the most common current panel font size) rather than storing an
  absolute point size directly, so it composes cleanly with the same
  per-rule base-size scaling the presets use.
- Persist as a single float under `QSettings("Ally", "DevInspectorWindow")`,
  key `"devFontScale"`, default `1.0`.
- Wire this into the same stylesheet-rebuild path from §1.5 (the
  `{dev_font_size}` token) — changing text size should call the same
  `_apply_active_theme()` (or a shared `_rebuild_dev_stylesheet()` helper
  that both the Theme menu and Text Size menu call) rather than being a
  separate, parallel styling mechanism.

### Phase 2 — verification / definition of done

- Selecting each preset visibly changes text size across all themed dev
  panels simultaneously.
- Custom size dialog accepts a point size and applies it correctly.
- Setting persists across a close/reopen of the dev inspector.
- Switching themes does NOT reset the chosen text size, and vice versa —
  confirm these two settings are independent.

---

## Phase 3 — JSON tree view for Scribe and Ally panels

Replace the current `QTextEdit` pretty-printed-JSON-as-plain-text display in
`interfaces/gui_qt/dev/panels/scribe_panel.py` and
`interfaces/gui_qt/dev/panels/ally_panel.py` with a `QTreeView` +
detail-pane combination.

### 3.1 — `JsonTreeModel`

Create `interfaces/gui_qt/dev/json_tree_model.py`:

- A `QAbstractItemModel` subclass (`JsonTreeModel`) that wraps an arbitrary
  Python value already converted to plain dict/list/scalar form (i.e. the
  panel does `output.model_dump()` — NOT `model_dump_json()` — and hands
  the resulting dict/list/scalar structure to the model; the model itself
  should not need to know about Pydantic).
- Internal node representation: a small dataclass (`_JsonNode`) holding
  `key: str | int | None` (dict key, list index, or `None` for root),
  `value: Any`, `parent: "_JsonNode" | None`, `children: list["_JsonNode"]`
  (built lazily or eagerly on model construction — eager is fine given
  these payloads are small).
- Two columns: **"Key"** and **"Value"**. For a dict/list node, the "Value"
  column shows a short type/count summary (e.g. `"{3 keys}"`, `"[5 items]"`)
  rather than trying to render the nested structure inline. For a scalar
  leaf node, "Value" shows the actual value, truncated with an ellipsis
  past some reasonable length (e.g. 80 characters) so long strings (Ally's
  `analysis` field especially) don't blow out row height or column width.
- Implement `data()` with `Qt.ItemDataRole.ForegroundRole` returning
  different colors per value type, pulled from the active `Theme` (don't
  hardcode hex here — accept a `Theme` instance or a small color-mapping
  dict in the model's constructor so it can be theme-aware too, consistent
  with everything else in this task): keys use `theme.accent_secondary`;
  string values use `theme.fg_primary`; numbers use `theme.success`;
  booleans/null use `theme.warning`; dict/list summary values use
  `theme.fg_muted`.
- Implement the standard `QAbstractItemModel` methods: `index()`,
  `parent()`, `rowCount()`, `columnCount()` (2), `data()`, `headerData()`.
- Add a method `full_value_for_index(index: QModelIndex) -> str` returning
  the **untruncated** string representation of that node's value (for a
  scalar: `str(value)`; for a dict/list: pretty-printed
  `json.dumps(value, indent=2)` of that subtree) — this feeds the detail
  pane in §3.2.

### 3.2 — Panel layout: tree + detail pane

In both `ScribePanel` and `AllyPanel`:

- Replace the single `QTextEdit` with a `QSplitter` (vertical orientation:
  tree on top, detail pane below), consistent with how `settings_dialog.py`
  and other multi-section widgets in this codebase are laid out.
- Top: `QTreeView` backed by a `JsonTreeModel` instance. Set a reasonable
  default column width for "Key" (e.g. 200px) and let "Value" stretch.
  Auto-expand exactly one level deep on load (top-level keys visible,
  everything below them collapsed) — implement via `QTreeView.expandToDepth(0)`
  after `setModel()`.
- Bottom: a read-only `QTextEdit` (word-wrap on, using the same
  `"devPanelText"` themed role from Phase 1) showing the full untruncated
  value of whatever tree node is currently selected. Wire
  `QTreeView.selectionModel().currentChanged` to call
  `model.full_value_for_index(current_index)` and push the result into
  this text edit. When nothing is selected (e.g. right after loading new
  data), show a placeholder like `"Select a node above to see its full value."`
- `handle_scribe_output()` / `handle_ally_output()` (the existing methods
  these panels expose, called from `CoreBridge` signals) should: call
  `.model_dump()` on the incoming output object (falling back to the
  existing `.dict()` / manual dict-building logic already present for
  non-Pydantic inputs — keep that fallback chain, just redirect its
  *output* into a new `JsonTreeModel` instead of into
  `json.dumps(..., indent=2)` text), construct a fresh `JsonTreeModel`,
  call `tree_view.setModel(new_model)`, then `tree_view.expandToDepth(0)`.
  Preserve the existing `None`-input handling (`"Awaiting ... output..."` /
  `"(Scribe skipped this turn)"` / `"(No Ally output)"`) — show that text
  in the detail pane (tree gets an empty/placeholder model) rather than
  removing that UX.
- These panels need to receive the active theme (for `JsonTreeModel`'s
  color mapping) the same way described in §1.6 — add a
  `set_active_theme(theme: Theme)` method, called by `DevInspectorWindow.
  _apply_active_theme()`, that stores the theme and, if a model is already
  loaded, rebuilds it with the new theme's colors (simplest correct
  approach: just re-run the last `handle_*_output()` call's stored raw
  value through a fresh model — keep the last raw dict cached on the panel
  for this purpose).

### Phase 3 — verification / definition of done

- Scribe and Ally panels show a navigable tree instead of a flat text blob.
- Selecting any node (including nested ones) shows that node's full value,
  word-wrapped, in the detail pane below — verified specifically with
  Ally's `analysis` field, which is the long-text case this was built for.
- Colors follow the active dev-inspector theme and update live on theme
  switch.
- Existing "awaiting output" / "skipped this turn" placeholder states still
  work correctly.

---

## Phase 4 — OCR panel redesign

Replace `interfaces/gui_qt/dev/panels/ocr_panel.py`'s single `QTextEdit`
with a structured layout:

- A **header strip** (a `QHBoxLayout` or small `QFormLayout` of `QLabel`s,
  not a text blob) showing: Screen Name, Confidence (formatted as today,
  `{:.2f}`), Is Draft Match (as a simple Yes/No or a checkbox-style
  indicator, read-only), Screen Category, Skip Reason. Use the
  `"devPanelTitle"` themed role (or a new small role if that doesn't fit
  visually — your judgment) for the labels so they pick up theme colors
  too.
- Below that, a `QTableWidget` (matching the pattern already used in
  `EntityPanel`/`TimingPanel`) with columns **Key / Value / Source**, one
  row per `ConfirmedFact`, sortable by clicking a column header
  (`setSortingEnabled(True)`).
- `handle_ocr_result(payload: dict)` keeps the same signature and input
  shape (called from the same `CoreBridge.ocr_result_ready` signal as
  today), but now updates the header labels' text directly and repopulates
  the table (clear + re-add rows, same pattern `EntityPanel._poll_entities()`
  already uses) instead of building one long formatted string.
- Apply the `"devPanelTable"` themed role (from Phase 1) to the new table
  so it matches `EntityPanel`/`TimingPanel` styling and responds to theme
  switching correctly.

### Phase 4 — verification / definition of done

- OCR panel shows a scannable header + sortable table instead of a text
  dump.
- Table responds to theme switching (background/text/gridlines) the same
  as other themed tables in the dev inspector.
- No behavior regression: the panel still updates correctly on every
  `on_ocr_result` emission during a live run.

---

## Documentation updates (required — do not skip)

This task involves genuine architectural decisions (new `theming/` package
placement and rationale, `Slate` rename, dynamic-property QSS mechanism,
exact-vs-hashed module color resolution strategy) as well as routine
implementation work. Both docs need updating, and they serve different
purposes — don't conflate them:

1. **`docs/ally_decision_log.md`** — add a new dated section (or a clearly
   titled section if you don't have today's date) covering:
   - Why `theming/` is a new top-level package rather than living under
     `infrastructure/` or `interfaces/` (the layering rationale: neither
     domain should depend on the other, both depend on a neutral shared
     package — same relationship `utils/event_hook.py` already has).
   - The `NEUTRAL_CONTENT_THEME` → `Slate` rename and why it's now a
     first-class, user-selectable theme rather than a hardcoded fallback.
   - The exact-dict-for-Slate vs. hashed-palette-for-Signal/Synthwave
     module-color resolution strategy, and why (curation cost vs. full
     coverage).
   - The dynamic-property QSS selector decision from Phase 0.2 (record
     whichever outcome actually occurred during implementation).
   - That the terminal is intentionally still hardcoded to `"Slate"` and
     not yet theme-switchable, and that this was a deliberate scope
     decision, not an oversight (so it doesn't get silently "fixed" by a
     future pass without someone deciding to do that on purpose).
2. **`docs/changelog.md`** — add a routine entry (matching the style of
   existing entries) listing the files touched, the new `theming/` package
   and its contents, the panels updated in each phase, and the new/changed
   test files.
3. **`docs/roadmap.md`** — remove any open item this task resolves (skim
   the file for entries about dev inspector styling if any exist), and add
   a new open item: **"Terminal theme switching"** — noted as explicitly
   deferred, not forgotten, per this task's Phase 1.3 comment in `logger.py`.
4. **`docs/THEMING.md`** — update to reflect: the `Slate` rename, the new
   `theming/` package split (what lives where and why), the new `Theme`
   fields (`font_mono`, `module_log_colors`, `log_level_colors`), the
   dev-inspector Theme menu and its independence from the overlay's theme
   selection, and the text-size setting from Phase 2. This file is
   explicitly meant to be the living reference for the theming system, so
   it needs to stay accurate — treat this as required, not optional
   polish.

---

## Notes for Claude's code review (ZooCode: ignore this section — it is not part of your task)

Things to specifically check when this comes back:

- Confirm Phase 0.1's diagnostic script's computed hex values actually made
  it into `Slate`'s `THEME_MODULE_COLORS`, rather than someone hand-copying
  slightly-off values under time pressure. Spot-check 2–3 against the
  formula myself.
- Confirm `theming/` truly has zero PySide6 imports — this is the entire
  point of the package split, and it's an easy rule to accidentally violate
  by importing something convenient from `interfaces/` "just this once."
- Check whether Phase 0.2 actually landed on dynamic properties or whether
  it hit the bail-out condition and something else got improvised instead
  — if the latter, that needs a real look, not a rubber stamp.
- Check that `resolve_module_color()`'s fallback chain is actually exercised
  correctly for Signal/Synthwave (i.e. they're genuinely resolving via
  hashed hues, not accidentally falling through to Slate's exact dict for
  every module due to a truthy-empty-dict-vs-missing-key bug — `{}.get(x)`
  vs `dict_missing_key` distinctions matter here).
- Verify the dev-inspector theme and the overlay theme are genuinely
  decoupled in the running app (open dev inspector, switch its theme, close
  it, reopen overlay settings, confirm overlay theme is unaffected and
  vice versa) — this was an explicit design requirement, easy to
  half-implement by accident if `QSettings` keys collide.
- Check `JsonTreeModel` performance/behavior isn't silently broken by a
  deeply nested or very large Scribe/Ally payload (MTGA's structured state
  in particular can get large) — not a hard requirement to optimize for in
  this pass, but worth a sanity check rather than discovering it live.
- Confirm the "additive over modificatory" convention was actually
  followed for the `NEUTRAL_CONTENT_THEME` alias — it should still work
  for any caller that wasn't updated, not just for the files this task
  happened to touch.
- Confirm all four documentation files listed above were actually updated,
  not just changelog.md (the easiest one to remember) — decision log and
  THEMING.md entries are easy to skip under time pressure and are exactly
  the ones with real lasting value here.
