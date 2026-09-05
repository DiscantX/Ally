# Task: Dev Inspector Theming — Remediation Pass

## Context (read before starting)

`CLAUDE_LED_TASK_dev_inspector_theming_and_views.md` ("the original task")
was implemented and reported complete in `docs/changelog.md` (2026-09-04 and
2026-09-05 entries) and `docs/THEMING.md`. In practice the app has been
throwing a cascading series of exceptions since that implementation landed.
A review against the original task file found:

1. **One real architectural defect** (a reversed package dependency) that
   is the most likely root cause of import-time exceptions that resurface
   in different forms as unrelated files are touched.
2. **One mandatory phase (1.4, the dev-inspector Theme menu) that was
   never implemented at all**, despite the changelog and `THEMING.md`
   both asserting it was.
3. **Several panels that were never converted** in Phase 1.5, despite the
   changelog listing that phase as complete.
4. **One confirmed, reproducible crash** (`VisionPanel._on_log_entry`)
   caused by a variable that is read but never initialized.

This task fixes all four in one consolidated pass, in dependency order —
do not skip ahead to a later section before the earlier one is verified,
since later fixes assume earlier ones are already in place.

**Follow CLAUDE.md and `.markdownlint.yaml` conventions throughout** (type
hints, no `# type: ignore`, dataclasses over dicts, logger
`MODULE_NAME`/`REGISTRY` pattern, additive-over-modificatory).

**This task has 4 phases, matching the 4 findings above. Subdivide into
sub-tasks along these boundaries** — Phase 0 must be fixed and verified
before touching anything else, since Phase 1–3 work is hard to test
reliably while the app can crash on import.

---

## Phase 0 — Fix the reversed package dependency (mandatory, do this first)

### 0.1 — The problem

`theming/palettes.py` currently contains:

```python
from interfaces.gui_qt.theming.palette_hash import color_for_key
```

This is backwards. The entire reason the top-level `theming/` package was
created (original task §1.1) was so that neither `infrastructure/` nor
`interfaces/` depends on the other — both depend on a neutral shared
package instead. `theming/palettes.py` importing from
`interfaces.gui_qt.theming.palette_hash` violates that directly: it makes
the "neutral" package depend on `interfaces.gui_qt`.

Because `infrastructure/logger/logger.py` imports `theming.palettes` at
module level, and `logger.py` is imported from nearly everywhere in this
codebase (including headless paths, e.g. the MTGA plugin test suite),
**every import of `logger.py` now transitively imports `interfaces/`,
`interfaces/gui_qt/`, and everything their `__init__.py` files pull in** —
even in contexts that have nothing to do with the GUI. This is almost
certainly why exceptions have been resurfacing unpredictably: fixing one
file doesn't address the actual defect, which is the dependency direction
itself.

### 0.2 — The fix

1. Move `color_for_key()` out of
   `interfaces/gui_qt/theming/palette_hash.py` and into the `theming/`
   package itself. Add it to `theming/color_convert.py`, OR create a new
   `theming/hashing.py` if you judge that cleaner — either is acceptable,
   but it must live in `theming/`, not in `interfaces/`.
2. Update `theming/palettes.py`'s import to pull from the new in-package
   location (e.g. `from theming.color_convert import color_for_key` or
   `from theming.hashing import color_for_key`).
3. `interfaces/gui_qt/theming/palette_hash.py` must keep working for any
   existing caller (`interfaces/gui_qt/theming/theme.py` does not appear
   to import it directly today, but `interfaces/gui_qt/prod/status_strip.py`
   and `interfaces/gui_qt/prod/message_formatting.py` do). Do **not**
   delete this file. Instead, make it a thin re-export:

   ```python
   """Deprecated location. color_for_key now lives in theming/ so that
   package can be imported without depending on interfaces.gui_qt. This
   module is kept as a compatibility re-export.
   """
   from theming.color_convert import color_for_key  # or theming.hashing

   __all__ = ["color_for_key"]
   ```

4. Grep the entire repo for `from interfaces.gui_qt.theming.palette_hash
   import` and `interfaces.gui_qt.theming.palette_hash` more generally.
   Every caller can keep importing from the old path (it still works via
   the re-export) — you do not need to update call sites — but paste the
   grep output into your completion notes so it's visible which callers
   exist today.

### 0.3 — Verification gate (mandatory before Phase 1)

Run, and paste the output of, all of the following:

```bash
python -c "import theming.palettes"
python -c "import infrastructure.logger"
python -c "import infrastructure.logger; import interfaces.gui_qt" 2>&1
```

Then confirm directly, by reading the file, that `theming/palettes.py`
and `theming/color_convert.py` (or `theming/hashing.py`) contain **zero**
references to `interfaces` anywhere. Paste:

```bash
grep -rn "interfaces" theming/
```

Expected output: nothing (empty). If this grep returns any match, Phase 0
is not done — stop and fix it before proceeding, do not move on to Phase 1
with this still present.

Also run the existing MTGA test suite (which has no GUI dependency at all)
to confirm it no longer transitively touches `interfaces.gui_qt`:

```bash
python -m unittest discover ingestion/plugins/mtga/tests -p "test_*.py"
```

Paste the output. This should pass exactly as it did before this task —
if it now fails on a new import error, Phase 0 introduced a regression.

---

## Phase 1 — Fix the confirmed `VisionPanel` crash

### 1.1 — The bug

`interfaces/gui_qt/dev/panels/vision_panel.py`'s `_on_log_entry` method:

```python
def _on_log_entry(self, entry: LogEntry) -> None:
    vision_brains = {"ScreenClassifier", "ScreenBootstrapper", "LayoutOCRReader", "OCR", "ClipClassifier", "CategoryStore"}
    if entry.brain_name in vision_brains or "vision" in entry.method_name.lower():
        line = f"[{entry.brain_name}] {entry.message}"
        self._log_tail.append(line)
        if len(self._log_tail) > 5:
            self._log_tail.pop(0)
        self._log_text.setPlainText("\n".join(self._log_tail))
```

references `self._log_tail`, which is **never initialized** anywhere in
`VisionPanel.__init__`. Only `self._log_entries: list[LogEntry] = []` is
initialized (and appears otherwise unused by this method). The first log
line emitted by any of `ScreenClassifier`, `ScreenBootstrapper`,
`LayoutOCRReader`, `OCR`, `ClipClassifier`, or `CategoryStore` during a
live run throws `AttributeError: 'VisionPanel' object has no attribute
'_log_tail'`.

### 1.2 — The fix

In `VisionPanel.__init__`, add the missing initialization alongside the
existing `self._log_entries: list[LogEntry] = []`:

```python
self._log_tail: list[str] = []
```

Also render this consistently with how other panels in this codebase
render their log tails (`MemoryPanel`/`OutputPanel` use rich HTML with
per-module/per-level coloring, per the original task's Phase 1.6). Since
Phase 1.6 of the original task specifically named `VisionPanel`'s log tail
as one of the two embedded tails that needed HTML coloring (the other
being `MemoryPanel`'s), and this method currently uses
`setPlainText()` with no coloring at all, fix this properly rather than
just patching the crash:

- Follow the exact pattern already used in `MemoryPanel._format_entry_html()`
  / `MemoryPanel._refresh_log_tail()` — resolve module color via
  `theming.palettes.resolve_module_color(self._active_theme_name, entry.brain_name)`
  and level color via `self._themes.get(self._active_theme_name, SLATE).log_level_colors`.
- `VisionPanel` already has `self._active_theme_name: str = "Slate"` and
  `self._themes = {"Slate": SLATE, "Signal": SIGNAL, "Synthwave": SYNTHWAVE}`
  declared in `__init__` — reuse these, do not add a second, parallel set
  of theme-name state.
- Change `self._log_text.setPlainText(...)` to
  `self._log_text.setHtml("<br>".join(html_lines))`, matching
  `MemoryPanel`/`OutputPanel`'s existing convention exactly.
- Rename `self._log_tail: list[str]` to store `LogEntry` objects instead
  of pre-formatted strings (`self._log_tail: list[LogEntry] = []`), so
  theme switches can re-render historical lines with new colors — this is
  the same pattern `OutputPanel._all_entries` and `MemoryPanel._log_entries`
  already use. Cap it at 5 entries as today (`if len(self._log_tail) > 5:
  self._log_tail.pop(0)`).

### 1.3 — Verification gate

- Confirm `VisionPanel.__init__` initializes `self._log_tail`.
- Manually trigger a log line from one of the six `vision_brains` module
  names (e.g. run the app against any configured game so
  `ScreenClassifier` logs at least once) and confirm no `AttributeError`
  is raised and the vision panel's log tail displays colored text.
- Confirm switching dev-inspector theme (once Phase 2 below adds the
  ability to do so) re-colors this panel's existing log tail history, not
  just future lines.

---

## Phase 2 — Actually build the dev-inspector Theme menu (Phase 1.4 of the original task)

### 2.1 — The problem

`docs/changelog.md`'s 2026-09-04 entry and `docs/THEMING.md`'s "Dev
Inspector Theme Menu & Independence" section both assert this exists:

> "Added a mutually exclusive Theme menu (Slate, Signal, Synthwave)
> backed by `QSettings` under `'devThemeName'`... fully independent of the
> main overlay window's theme selection."

This is not in the code. Verify this yourself before starting by reading
`interfaces/gui_qt/dev/dev_window.py`'s `_setup_menus()` method — it
builds only a `"&View"` menu (dock toggles, Text Size submenu, Reset
Layout) and a `"&Layout"` menu (save/load/export). There is no `"&Theme"`
menu, no `QActionGroup` for theme selection, no `_active_theme_name`
attribute, no `_apply_active_theme()` method, and no `QSettings` read/write
for a `"devThemeName"` key anywhere in the file.

The dev inspector's theme is currently still hard-wired from the outside:
`DevInspectorWindow.__init__(self, core, theme: Theme, ...)` takes a
`Theme` object directly, and `main.py`'s call site
(`DevInspectorWindow.get_instance(core, overlay._theme)`) passes the
**overlay's own active theme** — meaning the dev inspector and the prod
overlay are currently coupled, which is the exact thing this feature was
supposed to prevent.

### 2.2 — The fix

Build this for real, per the original task's §1.4 specification:

1. Add a **`"&Theme"`** menu to `_setup_menus()`, positioned before
   `"&Layout"`. Add three checkable `QAction`s — **Slate**, **Signal**,
   **Synthwave** — grouped under a `QActionGroup` with
   `setExclusive(True)`, matching the existing pattern already used for
   the Text Size presets a few lines below in the same method.

2. Add `self._active_theme_name: str` as an instance attribute, tracked
   separately from `self._theme: Theme` (keep `self._theme` as the
   resolved `Theme` object derived from `self._active_theme_name`, don't
   remove it — other code reads `self._theme`).

3. On `__init__`, resolve the persisted theme name from `QSettings("Ally",
   "DevInspectorWindow")` under a new key `"devThemeName"`, defaulting to
   `"Slate"` if unset (first run). Store it in `self._active_theme_name`,
   check the corresponding action in the Theme menu, and resolve
   `self._theme` from it via a small lookup:
   `{"Slate": SLATE, "Signal": SIGNAL, "Synthwave": SYNTHWAVE}[self._active_theme_name]`.

4. **`__init__`'s `theme: Theme` constructor parameter and
   `get_instance()`'s `theme: Theme` parameter should be treated as an
   initial-fallback/first-run hint only, not an override of a persisted
   choice.** If `QSettings` already has a `"devThemeName"` value, that
   value wins over whatever `theme` argument was passed in from
   `main.py`/`overlay._theme` — this is what "fully independent of the
   overlay" actually requires. Only use the passed-in `theme` argument
   when no persisted value exists yet.

5. Add a new method `_apply_active_theme(self) -> None` that:
   - Resolves `self._theme` from `self._active_theme_name`.
   - Calls `self._rebuild_stylesheet()` (already exists).
   - Propagates to every themed panel — see Phase 3 below for the full
     list this must call; do not only call the four panels the current
     (incomplete) `set_active_theme()` method calls today.
   - Persists the choice: `self._settings.setValue("devThemeName",
     self._active_theme_name)`.

6. Wire each of the three Theme menu actions' `triggered` signal to a
   handler that sets `self._active_theme_name` to the corresponding string
   and calls `self._apply_active_theme()`.

7. Call `self._apply_active_theme()` once at the end of `__init__` (after
   `_setup_docks()` and `_setup_menus()`), so panels render correctly with
   the persisted/default theme on first show — not only after a manual
   menu interaction.

8. Existing external callers of `set_active_theme(theme: Theme)` (i.e.
   `main.py`'s `_on_core_initialized` — check whether it calls this;
   `DevInspectorWindow.get_instance()` currently calls
   `cls._instance.set_active_theme(theme)` when the singleton already
   exists) should be updated to go through the new theme-name-based path
   rather than bypassing it. Since `get_instance()` is called from
   `main.py`/`system_tray.py` with the **overlay's** theme, and that must
   no longer be authoritative once a dev-inspector-specific choice exists,
   change `get_instance()`'s existing-instance branch to **not**
   override a previously-set `self._active_theme_name` — it should only
   matter on true first construction (see point 4 above). Rename or
   adjust `set_active_theme(theme: Theme)`'s call sites accordingly; you
   may keep a method with this exact old signature for compatibility if
   something else depends on it, but it must not be the mechanism the
   Theme menu itself uses internally, and it must not silently override a
   persisted user choice on every `get_instance()` call.

### 2.3 — Verification gate

- Open the dev inspector. Confirm a "Theme" menu exists between "View"
  and "Layout" with three checkable, mutually-exclusive entries.
- Switch to Synthwave in the dev inspector. Confirm every dock panel's
  chrome and text visibly changes.
- Close the dev inspector, reopen it (via the tray icon or status strip
  button). Confirm it reopens in Synthwave, not back to whatever the
  overlay is set to.
- Open the prod overlay's own Settings dialog and switch **its** theme
  (Signal ↔ Synthwave). Confirm the dev inspector's theme does **not**
  change as a side effect, and vice versa — switching the dev inspector's
  theme does not touch the overlay.
- Confirm the choice survives closing and relaunching the whole
  application (not just closing/reopening the dev inspector window within
  one process), by checking `QSettings("Ally",
  "DevInspectorWindow").value("devThemeName")` is actually being written.

---

## Phase 3 — Finish Phase 1.5 (QSS centralization) for the panels that were skipped

### 3.1 — Current state (verified by reading each file)

**Correctly converted** to the `"themed"` dynamic-property pattern (no
changes needed, listed for completeness):
- `interfaces/gui_qt/dev/panels/ocr_panel.py`
- `interfaces/gui_qt/dev/panels/timing_panel.py`
- `interfaces/gui_qt/dev/panels/memory_panel.py`
- `interfaces/gui_qt/dev/panels/output_panel.py`
- `interfaces/gui_qt/dev/panels/scribe_panel.py`

**Partially converted** — sets the `"themed"` property but never calls
`unpolish()`/`polish()` after, so the style will not reliably apply at
construction time (Qt requires the unpolish/polish cycle to force a style
re-evaluation after a dynamic property changes on an already-constructed
widget):
- `interfaces/gui_qt/dev/panels/ally_panel.py` — `self._detail_text.setProperty("themed", "devPanelText")` is set but there is no following `self._detail_text.style().unpolish(...)`/`.polish(...)` call.

**Not converted at all** — still using inline `setStyleSheet(f"...
{NEUTRAL_CONTENT_THEME...}...")`, exactly the pattern the original task
required removing:
- `interfaces/gui_qt/dev/panels/debug_panel.py` — `self._image_label.setStyleSheet(...)`
- `interfaces/gui_qt/dev/panels/entity_panel.py` — `self._table.setStyleSheet(...)`
- `interfaces/gui_qt/dev/panels/thinking_panel.py` — `self._text.setStyleSheet(...)`
- `interfaces/gui_qt/dev/panels/vision_panel.py` — multiple: `_create_pipeline_slot()`'s `card`/`title_lbl`/`img_lbl`, and `set_active_theme()`'s per-slot re-styling

**Inconsistent method signature** — `MemoryPanel.set_active_theme(self,
theme_name: str)` and `OutputPanel.set_active_theme(self, theme_name:
str)` take a theme **name string**, while `ScribePanel.set_active_theme(self,
theme: Theme)`, `AllyPanel.set_active_theme(self, theme: Theme)`, and
`OcrPanel.set_active_theme(self, theme: Theme)` take a **`Theme`
object**. `VisionPanel.set_active_theme(self, theme: Any)` also takes an
object. This inconsistency means `DevInspectorWindow` cannot call all
panels uniformly, and is part of why propagation was left incomplete.

**Not called from `DevInspectorWindow` at all** — `set_core()` only wires
signals for `_vision_panel`, `_entity_panel`, `_memory_panel`, and (once
Phase 2 above adds real propagation) themed panels are only reached via
whatever `set_active_theme()`/`_apply_active_theme()` currently calls,
which today is limited to `_scribe_panel`, `_ally_panel`, `_ocr_panel`,
`_vision_panel`. `debug_panel`, `entity_panel`, `timing_panel`,
`memory_panel`, `output_panel`, and `thinking_panel` are never reached by
any theme-propagation call today.

### 3.2 — The fix

**Step 1 — Standardize every panel's theme-update method to the same
signature.** Pick `set_active_theme(self, theme: Theme) -> None` (the
`Theme`-object form, matching the majority) as the standard across every
panel. Update `MemoryPanel` and `OutputPanel` to accept a `Theme` object
instead of a string, and derive the theme name internally from
`theme.name` wherever they currently use a bare name string (e.g.
`self._active_theme_name = theme.name`, then keep using
`self._themes.get(self._active_theme_name, SLATE)` as today, or simplify
to just storing `self._theme: Theme = theme` directly and dropping the
`self._themes` dict/lookup entirely — your call, but be consistent with
whichever approach the majority of already-correct panels use, don't
introduce a third pattern).

**Step 2 — Convert the four unconverted panels to the `"themed"` dynamic
property pattern**, following the exact recipe already used correctly in
`ocr_panel.py`/`scribe_panel.py`:

- `debug_panel.py`: apply `themed="devPanelSurface"` to `self._image_label`
  (this was explicitly named for this exact widget in the original task's
  §1.5 file list — "generic surface/background-only widgets like
  `debug_panel`'s image label"). Remove the inline `setStyleSheet(...)`
  call in `__init__`. Note this widget's text content changes dynamically
  (it shows either "Awaiting debug overlay frame..." or a rendered pixmap)
  — the QSS rule only affects background/text-color while no pixmap is
  set, which is correct and matches the original intent.
- `entity_panel.py`: apply `themed="devPanelTable"` to `self._table`,
  matching `ocr_panel.py`'s/`timing_panel.py`'s existing table styling
  exactly. Remove the inline `setStyleSheet(...)` call.
- `thinking_panel.py`: apply `themed="devPanelText"` to `self._text`.
  Remove the inline `setStyleSheet(...)` call. Note this panel's text is
  currently styled with `font-style: italic` inline, in addition to the
  color/font-family rules — if you want to preserve the italic styling,
  add a **new** narrow role (e.g. `themed="devPanelTextItalic"`) with a
  QSS rule identical to `devPanelText` plus `font-style: italic;`, rather
  than baking italics into the shared `devPanelText` rule (which would
  incorrectly italicize every other panel using that role).
- `vision_panel.py`: this one has multiple widgets per pipeline slot
  (`card`, `title_lbl`, `img_lbl`) created dynamically in
  `_create_pipeline_slot()`, plus a re-styling loop in
  `set_active_theme()`. Apply `themed="devPanelCard"` to each `card`
  (a `QFrame`; a `devPanelCard` role already exists as a described-but-
  possibly-unused convention — check whether `base.qss.tmpl` already has
  a `QWidget[themed="devPanelCard"]` rule, and add one if not, matching
  what `ocr_panel.py`'s header `QGroupBox` already declares via
  `header_group.setProperty("themed", "devPanelCard")`), `themed="devPanelTitle"`
  to each `title_lbl`, and `themed="devPanelSurface"` to each `img_lbl`.
  Remove the manual `card.setStyleSheet(...)`/`title_lbl.setStyleSheet(...)`/
  `img_lbl.setStyleSheet(...)` calls from both `_create_pipeline_slot()`
  and the loop inside `set_active_theme()` — once the dynamic property is
  set once at creation time, `unpolish()`/`polish()` on theme switch is
  sufficient and the manual re-styling loop becomes dead code.
- `ally_panel.py`: add the missing `self._detail_text.style().unpolish(self._detail_text);
  self._detail_text.style().polish(self._detail_text)` calls immediately
  after the existing `setProperty("themed", "devPanelText")` line.

**Step 3 — Wire `DevInspectorWindow._apply_active_theme()` (built in
Phase 2) to call `set_active_theme()` on every single themed panel**, not
just four of them:

```python
def _apply_active_theme(self) -> None:
    self._theme = {"Slate": SLATE, "Signal": SIGNAL, "Synthwave": SYNTHWAVE}[self._active_theme_name]
    self._rebuild_stylesheet()
    self._scribe_panel.set_active_theme(self._theme)
    self._ally_panel.set_active_theme(self._theme)
    self._ocr_panel.set_active_theme(self._theme)
    self._vision_panel.set_active_theme(self._theme)
    self._debug_panel.set_active_theme(self._theme)
    self._entity_panel.set_active_theme(self._theme)
    self._timing_panel.set_active_theme(self._theme)
    self._memory_panel.set_active_theme(self._theme)
    self._output_panel.set_active_theme(self._theme)
    self._thinking_panel.set_active_theme(self._theme)
    self._settings.setValue("devThemeName", self._active_theme_name)
```

(Exact method name/shape above is illustrative — match it to whatever you
actually named things in Phase 2, the point is that **all ten panels**
must be called, not a subset.) Every panel referenced here must expose a
`set_active_theme(self, theme: Theme) -> None` method after Step 1 above;
add one to any panel that doesn't have it yet (`debug_panel.py`,
`entity_panel.py`, `thinking_panel.py` currently have none at all — you
are adding these methods fresh, not just fixing existing ones).

### 3.3 — Verification gate (mandatory, do not skip)

1. Run this grep and paste the output:

   ```bash
   grep -rln "NEUTRAL_CONTENT_THEME\|SLATE\." interfaces/gui_qt/dev/panels/ | xargs grep -n "setStyleSheet"
   ```

   Expected output: **empty** (no remaining inline `setStyleSheet` calls
   referencing a theme constant directly in any dev panel file). If this
   returns any match, this phase is not done.

2. Confirm every file in `interfaces/gui_qt/dev/panels/` exposes a
   `set_active_theme(self, theme: Theme) -> None` method with that exact
   signature (grep for `def set_active_theme` across the directory and
   paste the output — visually confirm the parameter type on each).

3. Switch the dev-inspector theme via the Phase-2 Theme menu through all
   three options (Slate → Signal → Synthwave → back to Slate) and visually
   confirm **all ten** panels (Vision, Debug Overlay, OCR/Classification,
   Scribe, Ally, Entity Registry, Memory, Timing Waterfall, Logs,
   Thinking) change background/text/border color each time — not just the
   four that worked before this task.

---

## Documentation updates (required — do not skip)

1. **`docs/ally_decision_log.md`** — add a new dated section documenting:
   - The `theming/palettes.py` → `interfaces.gui_qt` reversed-dependency
     defect and the fix (moving `color_for_key` into `theming/`), stated
     plainly as a correction to the original task's own instructions (the
     original task told ZooCode to reuse `palette_hash.py` in place,
     without noticing this created the layering violation it explicitly
     told ZooCode to avoid).
   - That Phase 1.4 (Theme menu) was not implemented in the original pass
     despite being reported complete, and is implemented now.
   - The standardized `set_active_theme(theme: Theme)` signature decision
     across all dev panels, and that `MemoryPanel`/`OutputPanel` were
     changed from a string-based signature to match.

2. **`docs/changelog.md`** — add a new entry for this remediation pass.
   **Do not reuse or edit the 2026-09-04/2026-09-05 entries** — leave them
   as historical record of what was claimed, and add a new entry stating
   plainly that this pass corrected a reversed package dependency, added
   the previously-missing Theme menu, fixed the `VisionPanel` crash, and
   completed QSS conversion for the four panels that were skipped. Being
   explicit that the earlier entries overstated completion is intentional
   — don't soften this into "polish" language.

3. **`docs/THEMING.md`** — verify the "Dev Inspector Theme Menu &
   Independence" section now accurately describes the real, working
   mechanism (menu location, `QSettings` key, independence guarantee) —
   update wording if anything in this task's implementation differs in
   detail from what's currently written there.

4. **`docs/roadmap.md`** — no changes expected, but check whether "Dev
   Inspector Theming" or similar appears as an open item anywhere; if so,
   remove it now that this pass closes it out.

---

## Notes for Claude's code review (ZooCode: ignore this section — it is not part of your task)

Things to specifically re-verify when this comes back, given the previous
pass's changelog/doc claims did not match the actual code:

- **Don't trust the changelog entry this time either — verify by reading
  the files directly**, the same way this remediation task itself was
  derived from reading files rather than trusting prior documentation.
  Specifically re-run the Phase 0.3, Phase 1.3, Phase 2.3, and Phase 3.3
  grep/verification commands myself against the returned code, not just
  read ZooCode's pasted output.
- Confirm `theming/` genuinely has zero imports from `interfaces` anywhere
  in the package after the fix — re-run the grep myself.
- Confirm the Theme menu is real: open `dev_window.py` and check for an
  actual `"&Theme"` menu construction with three `QAction`s and a
  `QActionGroup`, not just a `_apply_active_theme` method that exists but
  is never wired to any menu.
- Confirm `QSettings` persistence actually wins over the `theme` argument
  passed into `get_instance()`/`__init__()` on a second call — this is the
  one place the original spec's "fully independent of the overlay" claim
  could get quietly half-implemented again (e.g. persisted correctly but
  still overridden every time `get_instance()` is called from
  `system_tray.py`/`main.py` with the overlay's theme).
- Spot-check that `unpolish()`/`polish()` calls were actually added
  everywhere a `setProperty("themed", ...)` call was added or already
  existed — this is an easy step to forget silently, and a panel that sets
  the property without the polish cycle will *look* converted in a code
  read but not actually re-theme correctly at runtime.
- Check whether the `thinking_panel.py` italic-preservation approach
  (separate `devPanelTextItalic` role vs. baking italics into
  `devPanelText`) was done correctly — if italics leaked into
  `devPanelText`, every other panel using that role will unexpectedly
  render in italics.
- Confirm the MTGA test suite (`python -m unittest discover
  ingestion/plugins/mtga/tests -p "test_*.py"`) still passes after the
  Phase 0 fix — this is the cheapest possible canary for "did the
  dependency-direction fix actually take," since that suite has no GUI
  dependency and should never import `interfaces.gui_qt` at all.
