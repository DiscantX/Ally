# CLAUDE_LED_TASK: PySide6 GUI Rewrite, Pipeline Introspection, Theming & Entity Highlighting

> Handoff spec from Claude to ZooCode. This document is the product of an
> extended design conversation and reflects deliberate, already-settled
> decisions — it is not a menu of options. Where a decision was genuinely
> left open, that is called out explicitly as such; everywhere else,
> implement exactly what is specified.

---

## 0. Context & Goal

`gui/` (Tkinter) is being replaced with a PySide6 shell, split into two
independent windows:

- **Prod overlay** — a small, translucent, edge-snapping companion panel
  that sits over the game. Player-facing.
- **Dev inspector window** — a separate, normal (opaque, taskbar-visible)
  desktop window exposing every stage of the pipeline for debugging.
  Developer-facing (Ficus) only.

Both windows are frontends to the *same* running `AllyCore` instance in
the *same* process — `AllyCore` itself is not being rewritten, and per
`ARCHITECTURE.md` it must remain GUI-framework-agnostic. This pass also
adds: a theming system (token-based, two built-in themes), a post-
processing entity-mention highlighter for the feed, and a "self-capture
exclusion" fix so Ally's own overlay windows never appear in the frames
it captures and comments on.

**Do not delete `gui/` (Tkinter) or the existing `--gui` flag in this
pass.** They stay functional in parallel until the new shell reaches
parity and is confirmed stable in real play. Removal is a separate,
future cleanup task.

---

## 1. Non-Negotiable Constraints

- Follow `CLAUDE.md`: full type hints, `Optional[...]`/`| None` explicit,
  dataclasses/Pydantic over loose dicts, no `# type: ignore` to silence
  Pylance — fix the actual type issue.
- Follow the project's autonomy principle: nothing built in this task may
  require a human to notice/open/approve something before the pipeline
  proceeds. GUI panels are for *observing* the pipeline, never a required
  gate in its path.
- Brain-region naming stays confined to module/package names and
  docstrings only, never class names (see `ally_decision_log.md`'s
  "Naming convention decision"). None of this task's new components are
  brain-region-analogous anyway, so this mostly just means: don't invent
  cute brain names for GUI classes.
- Use `logger.log()` for all logging, never a manual `[Tag]` prefix — see
  `CLAUDE.md`.
- Follow `.markdownlint.yaml` for any new `.md` files this task produces
  (`THEMING.md` — see Phase 2).
- Hand-code all widgets in Python. Do not introduce `.ui` files or
  `pyside6-uic` tooling — keep everything in versioned `.py`, consistent
  with how `gui/tkinter_app.py` is built today.

---

## 2. Phasing & Subdivision Instructions

**Use Architect mode to split this into one sub-task sequence per Phase
below, implemented and committed in order.** Phase 1 is a hard
dependency for every later phase — do not start Phase 4/5 widget code
before Phase 1 is complete and its call-site conversions (§4.1) are
verified. Phases 2 and 3 are independent of each other and of Phase 1's
internals (beyond needing `EventHook` to exist), and may be built in
parallel with each other. Phase 5 may be built in parallel with Phase 4.
Phase 6 depends on both 4 and 5 existing.

```
Phase 1 (foundational) ──┬──> Phase 2 (theming) ──┐
                          ├──> Phase 3 (highlighter)├──> Phase 4 (prod) ──┐
                          └──> Phase 5 (dev window) ─────────────────────┴──> Phase 6 (main.py wiring)
```

---

## 3. Dependency Changes

Add to `requirements.txt`:

```
PySide6
```

Do **not** add `PyQt6` — PySide6 only (LGPL licensing, no GPL obligation).

---

## 4. Phase 1 — Foundational Refactors

### 4.1 Observer pattern for `AllyCore` and `logger`

**Problem:** `AllyCore`'s `on_*` attributes (`ally/core.py`) are currently
single-slot `Optional[Callable]`, assigned with `=`. Two independent
windows subscribing to the same running core (plus keeping the old
Tkinter overlay alive in parallel per §0) requires multi-subscriber
support.

**Do not name the new utility class `Signal`** — PySide6 already has a
class called `Signal` (`PySide6.QtCore.Signal`) for defining Qt signals,
and this will cause confusion/collisions in GUI code that imports both.
Name it `EventHook`.

Create `utils/event_hook.py`:

```python
"""Minimal multi-subscriber observer utility. Deliberately NOT Qt's
QObject/Signal -- AllyCore and logger/logger.py must stay GUI-framework-
agnostic (see ARCHITECTURE.md's air-gap / GUI-agnostic principles), so
this file must never import PySide6 or any other GUI toolkit. A frontend
(prod overlay, dev window, or a future third shell) subscribes here.

IMPORTANT -- THREADING: emit() runs every subscriber callback
synchronously, on whatever thread called emit(). It does NOT marshal
onto a GUI toolkit's main thread. Qt-side subscribers must bridge each
EventHook into a real PySide6 Signal via a small QObject (see Phase 4/5
"CoreBridge" pattern) rather than touching widgets directly inside the
callback -- otherwise this will crash or silently corrupt Qt's internal
state when AllyCore emits from a background thread (e.g. send_message's
thread, or run_loop's thread).
"""
from typing import Callable
from logger import log


class EventHook:
    def __init__(self, name: str = ""):
        self._name = name
        self._subscribers: list[Callable] = []

    def connect(self, callback: Callable) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def disconnect(self, callback: Callable) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def emit(self, *args, **kwargs) -> None:
        for callback in list(self._subscribers):  # copy: a subscriber may disconnect during iteration
            try:
                callback(*args, **kwargs)
            except Exception as e:
                log("EventHook '{name}' subscriber raised: {e}", name=self._name, e=e, level="error")
```

**In `ally/core.py`:** convert every one of these attributes from
`Optional[Callable[...]] = None` to `EventHook("on_x")`:

`on_pipeline_image`, `on_debug_overlay`, `on_status_update`,
`on_state_summary`, `on_prompt_update`, `on_feedback`, `on_chat_message`,
`on_eta_ready`, `on_connection_status`, `on_medium_term`,
`on_personality_state`, `on_strategic_memory`.

Then convert every internal invocation from direct-call to `.emit(...)`,
and **remove the now-unnecessary `if self.on_x is not None:` guards** —
`EventHook.emit()` is always safe to call with zero subscribers. Search
`ally/core.py` for every occurrence of each hook name above being called
(not assigned) and convert it. Note: `on_connection_status` is currently
never invoked anywhere inside `ally/core.py` despite being defined —
leave it as an `EventHook` for API consistency, but do not invent a new
invocation site for it in this pass.

**Update every existing assignment call site** (these currently do
`core.on_x = some_callable`, which will silently break once `on_x` is an
`EventHook` instance rather than a plain attribute — an `EventHook`
object does not support `=` reassignment as a subscribe mechanism):

| File | What to change |
|---|---|
| `main.py`, headless branch of `initialize_application()` | `core.on_status_update = lambda...` → `core.on_status_update.connect(lambda...)`, and likewise for `on_state_summary`, `on_prompt_update`, `on_feedback`, `on_chat_message`, `on_connection_status` |
| `gui/tkinter_app.py`, `AllyOverlay.__init__` | Every `core.on_x = self.method_or_lambda` → `core.on_x.connect(self.method_or_lambda)`, for all twelve hooks listed above |

Add the identical `EventHook` pattern to `logger/logger.py`:

```python
_subscribers: list[Callable[["LogEntry"], None]] = []

def subscribe(callback) -> None: ...
def unsubscribe(callback) -> None: ...
```

Define a small `LogEntry` dataclass (`brain_name: str`, `method_name: str`,
`message: str`, `level: str`, `timestamp: datetime`) and, inside `log()`,
after the existing print/file-write logic (do not change that existing
behavior), notify every subscriber with a `LogEntry`. Wrap subscriber
calls in the same try/except-and-log-error pattern as `EventHook.emit()`
so a broken dev-panel subscriber can never take down logging itself.

**Expand `REGISTRY` in `logger/logger.py`** to cover the pipeline files
that dev-mode panels need to route by (currently missing entirely — they
fall through to `DEFAULT_BRAIN`/"General"):

| File | `name` | `color` |
|---|---|---|
| `screen_classifier.py` | `ScreenClassifier` | `mint` |
| `screen_bootstrapper.py` | `ScreenBootstrapper` | `salmon` |
| `layout_reader.py` | `LayoutOCRReader` | `teal` |
| `ocr.py` | `OCR` | `olive` |
| `clip_classifier.py` | `ClipClassifier` | `violet` |
| `screen_category_store.py` | `CategoryStore` | `lavender` |
| `entity_registry.py` | `EntityRegistry` | `sky_blue` |
| `narrative.py` | `NarrativeMemory` | `pink` |
| `personality.py` | `PersonalityMemory` | `purple` |
| `save_tracker.py` | `SaveTracker` | `dark_grey` |

### 4.2 `TurnTrace` — bounded, always-on pipeline snapshot

Create `state/turn_trace.py`. This exists **unconditionally**, dev mode
or not — it's cheap (references to data already computed each turn, not
new computation) and having it always populated means dev mode can be
opened mid-session without losing history.

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class TurnTrace:
    turn: int
    timestamp: float
    screen_name: str
    screen_confidence: float
    is_draft_match: bool
    skip_scribe_reason: str
    skip_ally: bool
    screen_category: str | None
    confirmed_facts: list[Any]          # collectors.base.ConfirmedFact
    scribe_output: Any | None           # schema.schema.ScribeOutput, None if skipped
    ally_output: Any | None             # schema.schema.AllyOutput, None if skipped
    prompt_sent_to_ally: str | None     # dev-only detail; may be large, that's fine, ring buffer is bounded
    timings: dict[str, float] = field(default_factory=dict)  # stage_name -> seconds
```

Add a bounded ring buffer to `AllyCore.__init__`:
`self.turn_traces: deque[TurnTrace] = deque(maxlen=20)`.

In `run_turn()`, wrap each named stage with `time.perf_counter()` and
accumulate into a `timings` dict (`"capture"` is already known by the
caller in `run_loop()`/timed at the collector level — just capture what's
available inside `run_turn()` itself: `"scribe"`, `"ally"`,
`"entity_resolve"`, `"memory_record"`). Build a `TurnTrace` at the end of
`run_turn()` (whether or not Scribe/Ally actually ran that turn — capture
what's available either way) and `self.turn_traces.append(trace)`. This
requires no new `EventHook` — the dev window reads `core.turn_traces`
directly (same process, see §8).

### 4.3 Self-capture exclusion

Two layers, both always active — not "fallback only if the other fails."

**A. `SetWindowDisplayAffinity`.** Create
`gui_qt/shell/capture_exclusion.py` (Windows-only, consistent with the
rest of the capture stack):

```python
import ctypes
from logger import log

WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011

def exclude_hwnd_from_capture(hwnd: int) -> bool:
    """Best-effort: excludes this top-level window from screen capture at
    the DWM compositor level (Windows 10 build 19041+). On older Windows
    builds this silently degrades to WDA_MONITOR behavior (a blank black
    rectangle in captures, rather than true exclusion) -- this is why
    the blackout-mask fallback (state/shell_bounds_registry.py +
    ScreenCollector) must always run regardless of this call's result,
    never conditionally on it."""
    try:
        ok = bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
        if not ok:
            log("SetWindowDisplayAffinity failed for hwnd={hwnd}", hwnd=hwnd, level="warning")
        return ok
    except Exception as e:
        log("SetWindowDisplayAffinity call raised: {e}", e=e, level="warning")
        return False
```

Call this once per shell window, after the widget has a native handle
(`int(widget.winId())`), for both the prod overlay and the dev window.

**B. Blackout-mask fallback (always runs, regardless of A's result).**
Create `state/shell_bounds_registry.py` — a thread-safe registry, same
locking convention as `EntityRegistry`:

```python
import threading

class ShellBoundsRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._bounds: dict[str, tuple[int, int, int, int]] = {}  # shell_id -> (left, top, width, height), absolute screen coords

    def update(self, shell_id: str, left: int, top: int, width: int, height: int) -> None:
        with self._lock:
            self._bounds[shell_id] = (left, top, width, height)

    def unregister(self, shell_id: str) -> None:
        with self._lock:
            self._bounds.pop(shell_id, None)

    def all_bounds(self) -> list[tuple[int, int, int, int]]:
        with self._lock:
            return list(self._bounds.values())

SHELL_BOUNDS = ShellBoundsRegistry()  # module-level singleton, imported by both collectors/screen_collector.py and the Qt shells
```

Each shell calls `SHELL_BOUNDS.update(...)` on move/resize/show, and
`SHELL_BOUNDS.unregister(...)` on close/hide.

In `collectors/screen_collector.py`'s `capture_bgr()`, immediately after
`frame = cv2.cvtColor(...)` and before returning: for each rect in
`SHELL_BOUNDS.all_bounds()`, translate from absolute screen coordinates
to frame-local pixel coordinates by subtracting `self.rect.left` /
`self.rect.top`, clip to `[0, frame width/height]`, and if the clipped
region has positive area, `cv2.rectangle(frame, (x0,y0), (x1,y1), (0,0,0), -1)`.
This must run unconditionally, every capture, cheap no-op when there's no
overlap. This is distinct from `ChangeDetector.set_ignore_regions()` —
that only affects the diff comparison; this actually removes the overlay
from the pixels handed to Scribe.

---

## 5. Phase 2 — Theming System

Raw Qt Style Sheets do **not** support CSS custom properties/`var()` —
confirmed, this is not a Qt-version gap that will resolve itself later.
Themes are therefore **token dataclasses**, rendered into a QSS string at
startup via a Python template, not swapped `:root{}` blocks.

### 5.1 Token schema

Create `gui_qt/theming/theme.py`:

```python
from dataclasses import dataclass, field

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
    companion_palette: list[str] = field(default_factory=list)  # 5-8 hex colors, used for deterministic personality/entity name-label coloring
```

### 5.2 Built-in themes — exact values

Do not invent new colors for these two. Both are derived directly from
values already in the codebase, so they stay visually consistent with
existing assets (the splash screen, the current overlay).

**`Signal`** (default, derived from `gui/models.py`'s `OverlayConfig`
and `gui/settings_window.py`'s dark-theme constants):

```python
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
)
```

**`Synthwave`** (derived from `run.py`'s `M_SHADES`/`C_SHADES` splash
gradient — converted from their ANSI `38;2;r;g;b` codes to hex):

```python
SYNTHWAVE = Theme(
    name="Synthwave",
    bg_base="#14101f",
    bg_surface="#1e1830",
    bg_elevated="#281f40",
    fg_primary="#e6e6f5",
    fg_secondary="#b8b3d1",
    fg_muted="#7a7599",
    border="#3a3355",
    accent_primary="#00f0f0",   # C_SHADES[0]
    accent_secondary="#ff2ddc", # M_SHADES[0]
    success="#00cc77",          # kept standard -- functional colors (success/warning/error) stay consistent across themes for legibility, only accent/companion colors vary
    warning="#ff9900",
    error="#c93b55",
    focus_ring="#00f0f0",
    companion_palette=["#ff2ddc", "#cd24ba", "#9b1b98", "#00f0f0", "#01bcca", "#0289a5"],
    # Note: darkest two steps of each original 5-step gradient (#691276, #370a55, #03567f)
    # are deliberately excluded from companion_palette -- too low-contrast as text-label
    # color against a dark background.
)
```

`bg_base`/`bg_surface`/`bg_elevated` for Synthwave are new (no direct
prior-art in the codebase) — reasonable dark-indigo values matching the
gradient's hue, not derived from anything specific; feel free to iterate
on these three specifically if they read poorly in practice, but do not
alter `accent_primary`/`accent_secondary`/`companion_palette` without
asking, since those are load-bearing brand-consistency decisions.

### 5.3 `NEUTRAL_CONTENT_THEME` — dev-mode content areas only

Per explicit decision: dev-window **chrome** (title bars, dock-tab
highlights, panel headers) follows the active user theme. Dev-window
**content** (JSON viewers, the Output/Logs panel, raw data displays)
stays on a fixed, theme-independent, neutral palette for legibility —
not user-selectable in this pass, but built as a real `Theme` instance
(not hardcoded literals scattered through widget code), so making it
selectable later is a config change, not a rewrite:

```python
NEUTRAL_CONTENT_THEME = Theme(
    name="NeutralContent",
    bg_base="#1e1e1e", bg_surface="#252526", bg_elevated="#2d2d2d",
    fg_primary="#d4d4d4", fg_secondary="#9d9d9d", fg_muted="#6a6a6a",
    border="#3c3c3c",
    accent_primary="#569cd6", accent_secondary="#4ec9b0",
    success="#6a9955", warning="#dcdcaa", error="#f44747",
    focus_ring="#569cd6",
    companion_palette=["#569cd6", "#4ec9b0", "#c586c0", "#ce9178", "#dcdcaa", "#9cdcfe"],
)
```

(These are VSCode's own dark-theme editor colors — a deliberate choice,
since dev-mode content panels are explicitly meant to feel like an IDE.)

### 5.4 QSS generation

Create a template file (`gui_qt/theming/base.qss.tmpl`) with `{token_name}`
placeholders and a function:

```python
def build_stylesheet(theme: Theme, template_path: str) -> str:
    with open(template_path, "r") as f:
        template = f.read()
    return template.format(**theme.__dict__)
```

Called once at each window's construction: `self.setStyleSheet(build_stylesheet(active_theme, TEMPLATE_PATH))`.

**Custom QSS override (tier-2 theming for advanced/3rd-party authors):**
if a `custom_qss_path` is set in `user_config.json` and the file exists,
load its raw contents and use that as the stylesheet instead of the
generated one. No merging logic needed — it's a full replacement. This is
cheap to support and should be included in this pass.

### 5.5 Object naming convention — mandatory for every widget

Every widget gets an `objectName`, scoped with a double-underscore
parent/child prefix, so a stylesheet author can predict names without
reading source. Examples (not exhaustive — follow the pattern for every
new widget):

`feedPanel`, `feedPanel__scrollArea`, `messageRow`, `messageRow__nameLabel`,
`messageRow__bodyLabel`, `inputBar`, `inputBar__textEdit`,
`inputBar__sendButton`, `inputBar__modeToggle`, `statusStrip`,
`statusStrip__connectionDot`, `statusStrip__personalityBadge`,
`statusStrip__thinkingIndicator`, `devDock__visionPanel`,
`devDock__ocrPanel`, `devDock__scribePanel`, `devDock__allyPanel`,
`devDock__entityPanel`, `devDock__memoryPanel`, `devDock__outputPanel`,
`devDock__timingPanel`.

Use Qt dynamic properties for **semantic state**, not widget identity, so
QSS can select on it: `messageRow` gets a custom property `speaker` set
to `"ally"` / `"player"` / `"system"`; Output-panel log-line widgets get
a property `level` set to `"debug"`/`"info"`/`"warning"`/`"error"`/`"critical"`.
Set via `widget.setProperty("speaker", "ally")`, and remember Qt requires
a style re-polish after a dynamic property changes on an already-visible
widget (`widget.style().unpolish(widget); widget.style().polish(widget)`).

### 5.6 Deliverable: `docs/THEMING.md`

Write a doc (following `.markdownlint.yaml`) covering: the full token
list with a one-line description of what each is for, both built-in
themes' values, the object-naming convention with examples, the dynamic-
property convention, and how to supply a custom QSS override file. This
is the actual artifact a 3rd party would read — write it for that
audience, not as internal notes.

### 5.7 Deterministic color-from-palette function

Needed by both the personality name-label coloring (§7) and the entity
highlighter (§6). Create `gui_qt/theming/palette_hash.py`:

```python
import hashlib

def color_for_key(key: str, palette: list[str]) -> str:
    """Deterministic, stable across process restarts -- do NOT use Python's
    built-in hash() here, it's salted per-process (PYTHONHASHSEED) and
    will assign a different color to the same key every run."""
    if not palette:
        return "#ffffff"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(palette)
    return palette[index]
```

---

## 6. Phase 3 — Entity Mention Highlighting

Runs as **post-processing on Ally's already-generated text**. Ally is
never asked to tag its own output — this keeps the highlighter fully
decoupled from prompt/voice quality (see the bracket-tag lesson already
recorded in `ally_decision_log.md`/`prompts/ally.py`: *"Never use square
brackets in the spoken dialogue"*).

This module has **zero Qt/GUI imports** — it's a pure function, testable
without PySide6 installed, and belongs near the data it reads, not in
`gui_qt/`.

### 6.1 Public accessor on `EntityRegistry`

`state/entity_registry.py`'s `_name_lookup()` is private. Add a public
wrapper rather than reaching into the private method from outside the
class:

```python
def name_lookup(self) -> dict[str, str]:
    """Public accessor for the current name/alias -> entity_id lookup, for
    consumers outside EntityRegistry (e.g. GUI-side entity highlighting)."""
    return self._name_lookup()
```

### 6.2 `state/entity_highlighter.py`

```python
"""Post-processing pass that finds entity mentions inside Ally's already-
generated spoken text, for GUI-side highlighting. Runs AFTER generation --
Ally is never asked to tag its own output (see ally_decision_log.md's
bracket-tagging lesson: asking a model to reliably self-delimit inside
natural prose hurt voice quality). Zero Qt/GUI dependency -- rendering
(color lookup, HTML wrapping) is entirely the GUI layer's job.
"""
import re
from dataclasses import dataclass
from state.entity_registry import EntityRegistry

MIN_NAME_LENGTH = 3  # skip trivial/very short names to avoid false-positive substring matches


@dataclass
class HighlightSpan:
    start: int
    end: int
    entity_id: str
    matched_text: str


def find_entity_mentions(text: str, registry: EntityRegistry) -> list[HighlightSpan]:
    if not text:
        return []
    lookup = registry.name_lookup()  # lowercased name/alias -> entity_id
    candidates = [name for name in lookup if len(name) >= MIN_NAME_LENGTH]
    if not candidates:
        return []
    candidates.sort(key=len, reverse=True)  # longest-match-first, so "Marcus the Bold" wins over "Marcus" when both are known aliases
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(re.escape(name) for name in candidates) + r")(?!\w)",
        re.IGNORECASE,
    )
    spans: list[HighlightSpan] = []
    for match in pattern.finditer(text):  # finditer's matches are already non-overlapping by construction
        entity_id = lookup.get(match.group(1).lower())
        if entity_id is None:
            continue
        spans.append(HighlightSpan(match.start(), match.end(), entity_id, match.group(1)))
    return spans
```

### 6.3 GUI-side rendering (Phase 4, but specified here since it's tightly coupled to §6.2's output)

Create `gui_qt/prod/message_formatting.py`. Given `analysis: str`,
`registry: EntityRegistry`, and the active `Theme`:

1. Call `find_entity_mentions(analysis, registry)` to get spans **against
   the raw, unmodified text** — do this before any Markdown processing,
   since Markdown syntax characters would shift character offsets.
2. Walk the spans **right-to-left by `span.start` descending** and wrap
   each matched substring with `<span style="color:{color};">...</span>`,
   where `color = color_for_key(span.entity_id, theme.companion_palette)`
   (hash on `entity_id`, not the matched text, so different aliases of
   the same entity always get the same color). Right-to-left insertion
   order is required so earlier insertions don't invalidate the offsets
   of spans still to be processed.
3. Feed the resulting string (raw text with `<span>` tags now embedded)
   through a Markdown-to-HTML pass — either Qt's own
   `QTextDocument.setMarkdown()` + `.toHtml()` round-trip, or the `markdown`
   PyPI package if the Qt round-trip doesn't cleanly preserve embedded
   inline HTML (verify this behavior; if raw `<span>` tags get escaped/
   mangled, use the `markdown` package with `output_format="html"` instead,
   which passes inline HTML through untouched by default).
4. Set the message widget's text with rich-text rendering (`QLabel` with
   `setTextFormat(Qt.TextFormat.RichText)`) using the final HTML string.

**Every feed message row widget must be built rich-text-capable from the
start** (per §7 below), even though most messages today will render as
plain prose with zero highlighted spans — this is a required
architectural choice for this pass, not a "nice to have," since retrofitting
a plain `QLabel.setText()` widget to rich text later is a real rewrite.

---

## 7. Phase 4 — Prod Overlay Shell

Directory: `gui_qt/prod/`.

### 7.1 Window shell

- `QWidget` (or `QMainWindow` with no menu/status bar chrome), flags:
  `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool` (the `Tool`
  flag keeps it out of the taskbar/alt-tab, appropriate for an overlay).
- `setAttribute(Qt.WA_TranslucentBackground, True)`; actual visible
  background/rounded corners drawn via QSS on an inner container widget
  (translucent top-level window + an opaque-but-themed child container is
  the standard PySide6 pattern for rounded, translucent overlays).
- On show and whenever the native handle becomes valid, call
  `exclude_hwnd_from_capture(int(self.winId()))` (§4.3-A).
- On every move/resize event, call
  `SHELL_BOUNDS.update("prod_overlay", ...)` (§4.3-B) with current
  absolute screen geometry; call `SHELL_BOUNDS.unregister("prod_overlay")`
  on close/hide.

### 7.2 Dragging & edge-snap

- Free drag via mouse press/move on a designated drag-handle region (a
  thin top strip, same pattern as `_start_move`/`_do_move` in the current
  Tkinter overlay).
- On `mouseReleaseEvent` after a drag: check distance from each of the
  four edges of `QScreen.availableGeometry()` for the screen the window
  center is currently on. If within a configurable threshold (default
  `28px`, config key `overlay_snap_threshold_px`), snap flush to that
  edge and record `self._snapped_edge: Literal["left","right","top","bottom"] | None`.
- **Resize constraint while snapped:** snapped left/right → width is
  fixed to a configured docked width (`overlay_docked_width_px`, default
  `340`), only height is user-resizable. Snapped top/bottom → the
  reverse. Unsnapped → freely resizable both axes within
  `min`/`max` bounds already present in `OverlayConfig`-equivalent config.
- **Expand-to-full-chat while snapped:** per settled decision, grows
  inward/vertically, edge-anchored side never moves, capped at a
  configured max width (`overlay_expanded_max_width_px`) so it can never
  overrun the game window.
- **Idle peek/collapse:** implement as a user setting
  (`overlay_peek_on_idle: bool`, default `False`; `overlay_peek_idle_seconds: int`,
  default `8`). When `True`, snapped, and idle (no mouse hover over the
  window, no new feed message) for the configured duration, animate to a
  small peeking tab flush with the edge (an accent-colored sliver with a
  small icon); hover or click restores full visibility. This can ship as
  a stub (setting exists, defaults to off, collapse logic is a smaller
  follow-up) if time-constrained within this phase — it is lower priority
  than the rest of §7.

### 7.3 Feed panel

- `QScrollArea` containing a `QVBoxLayout` of message-row widgets.
  Discord/Slack-style: no bubble background/border, each row is a colored
  `messageRow__nameLabel` (color from `color_for_key(speaker_id, theme.companion_palette)`
  — for Ally, `speaker_id` is the active personality name string; for the
  player, use a fixed neutral color, not palette-hashed) above/beside a
  `messageRow__bodyLabel` built per §6.3.
- Auto-scroll-to-bottom on new message **unless the user has manually
  scrolled up** — reuse the same "am I at the bottom" check pattern
  already present in `gui/chat_drawer.py`'s `_is_scrolled_to_bottom`.
- Set `speaker` dynamic property on each row per §5.5.

### 7.4 Input bar

- Always visible at the bottom (not a separate toggled drawer). Single-
  line by default; `Enter` sends, `Shift+Enter` inserts a newline.
- A mode toggle (small icon button, not a radio-button row) switching
  between "chat" and "feedback" — functionally the same distinction
  `gui/chat_drawer.py` already has via `message_type_var`, just
  presented compactly.
- An expand affordance (chevron icon) that triggers the "full chat" state
  from §7.2 — grows the input to multi-line and the feed panel to show
  more history.

### 7.5 Status strip

- Connection dot (reuse `core.on_connection_status`, even though it's
  currently never emitted internally — see §4.1's note; it's still valid
  for this widget to subscribe defensively).
- Personality badge: name + a small color swatch using
  `color_for_key(personality_name, theme.companion_palette)`.
- A subtle "thinking/composing" indicator (animated dots or pulsing
  accent-colored dot) shown while awaiting an Ally response — replaces
  the old literal ETA countdown/progress bar entirely; do not port the
  seconds-remaining display into prod mode.
- A small settings-gear icon and a "Dev" icon/button (opens the dev
  window — see §8; also add this as a system tray context-menu item).
  Do not build a global OS-level hotkey for summoning the dev window in
  this pass — the icon/tray-menu path is sufficient for v1; a true
  global hotkey (needed since the game will usually have OS focus) is
  deferred (see §10).

### 7.6 Settings dialog (minimal scope for this pass)

Rebuild `gui/settings_window.py` in PySide6, but **scope this down**:
this pass only needs a **theme picker** (dropdown: `Signal` / `Synthwave`
/ any theme discoverable via `custom_qss_path`) and the existing
**personality picker**. Full parity with the current Tkinter settings
window (model overrides, thinking-level sliders, threshold sliders,
downscaling controls) is explicitly deferred — see §10. All settings
still read/write through the existing `configs/config_manager.py`
functions unchanged; no new config-storage mechanism.

---

## 8. Phase 5 — Dev Inspector Window

Directory: `gui_qt/dev/`. A **separate `QMainWindow`**, normal desktop
window: not frameless, not always-on-top, real title bar, appears in the
taskbar/alt-tab, freely resizable. Opened from the prod overlay's
icon/tray menu (§7.5); singleton — if already open, raise and focus
rather than opening a second instance.

- On show, call `exclude_hwnd_from_capture(...)` and register bounds with
  `SHELL_BOUNDS` (§4.3), exactly like the prod overlay — the dev window
  can also end up positioned over the game, so it needs the same
  protection.
- Use `QDockWidget` for every panel below — dockable, tabbable,
  rearrangeable, VSCode-style. Persist layout via `QMainWindow.saveState()`/
  `.restoreState()`, stored through `QSettings` (organization/app name —
  this is a distinct, idiomatic-Qt persistence mechanism, do not reuse
  `user_config.json` for window/dock geometry).
- Chrome (dock title bars, tab highlights, splitter handles) uses the
  active user theme; every panel's **content area** uses
  `NEUTRAL_CONTENT_THEME` (§5.3) — apply the neutral theme's stylesheet
  scoped to each panel's inner content widget specifically, not the dock
  chrome around it.

### 8.1 Panels

| Panel | Data source | Update mechanism |
|---|---|---|
| **Vision Pipeline** | `core.on_pipeline_image` (existing hook — observation, grayscale, masked_grayscale, normalized_grayscale, diff, thresh, classifier_gray, classifier_crop) | Subscribe via `EventHook.connect`, bridge to a Qt signal (see §8.2) |
| **Debug Overlay** | `core.on_debug_overlay` (existing hook — annotated layout-box frame) | Same as above |
| **OCR / Screen Classification** | **New**: add `on_ocr_result: EventHook` to `AllyCore`, emitting a small dataclass (`screen_name`, `confidence`, `is_draft`, `confirmed_facts: list[ConfirmedFact]`, `screen_category: str \| None`, `skip_scribe_reason: str`) — this data already exists inside `run_turn()`/the `RawObservation`, it's just never surfaced past `log()` today. Emit once per turn from `run_turn()`. | Subscribe + bridge |
| **Scribe** | **New**: add `on_scribe_output: EventHook` emitting the raw `ScribeOutput` (or `None` when skipped, with the skip reason) | Subscribe + bridge; render as pretty-printed JSON (`model_dump_json(indent=2)`, Pydantic) |
| **Ally** | **New**: add `on_ally_output: EventHook` emitting the full `AllyOutput` object (existing `on_feedback` only carries the `analysis` string, not `actions`/`run_boundary`) | Subscribe + bridge; pretty-printed JSON |
| **Entity Registry** | `core.registry` (already a public attribute) | **Poll, don't push** — same-process, so a `QTimer` (~1s interval) reading `core.registry._entities.values()` into a `QTableView`/`QTableWidget` is simpler than adding a new per-turn signal for read-only table data |
| **Memory** | `core.memory_manager` (already public) — `get_medium_term_summaries()`, `get_long_term_summary()`, `get_cross_session_summary()`, `build_context()` | Poll via `QTimer`, same reasoning as Entity Registry — no core changes needed here beyond what already exists |
| **Timing Waterfall** | `core.turn_traces` (§4.2) | Poll via `QTimer`, render latest `TurnTrace.timings` as a simple bar/table breakdown per stage |
| **Output / Logs** | Logger pub/sub (§4.1) | Subscribe; single VSCode-Output-style panel with a channel dropdown built from `REGISTRY` names + `"All"` (default) |
| **Thinking** | **Not in scope for this pass.** Ship as a stub panel with placeholder text: *"Pending research — whether Gemini's structured-output mode exposes thought summaries needs verification before this panel can be built."* Do not attempt to implement real thinking-trace capture; do not modify `GeminiProvider.generate_structured()`'s request shape. | — |

Note that `on_ocr_result` deliberately bundles the CLIP/category
information into the same payload as screen classification/OCR, rather
than adding a fourth new hook — avoid further signal sprawl beyond the
three genuinely new hooks listed (`on_ocr_result`, `on_scribe_output`,
`on_ally_output`).

**Embedded log tails:** per explicit request, the Vision Pipeline panel
and the Memory panel should each also show a small one-line log tail
(last ~5 entries) scoped to their relevant `REGISTRY` channel(s), so
high-frequency vision-stage logging is visible at a glance without
flooding the main Output panel or the terminal. This is a small filtered
view onto the same log subscription already wired for the Output panel —
not a separate logging mechanism.

### 8.2 Cross-thread marshalling (critical, re-stated from §4.1)

Every `EventHook` subscription in the dev window (and prod overlay) must
bridge through a `QObject` subclass that re-exposes the data via a real
PySide6 `Signal`, so Qt's queued-connection thread marshalling applies
when `AllyCore` emits from a background thread:

```python
from PySide6.QtCore import QObject, Signal

class CoreBridge(QObject):
    scribe_output_ready = Signal(object)
    ally_output_ready = Signal(object)
    ocr_result_ready = Signal(object)
    # ... one per subscribed hook

    def __init__(self, core: "AllyCore"):
        super().__init__()
        core.on_scribe_output.connect(lambda payload: self.scribe_output_ready.emit(payload))
        core.on_ally_output.connect(lambda payload: self.ally_output_ready.emit(payload))
        core.on_ocr_result.connect(lambda payload: self.ocr_result_ready.emit(payload))
        # ...
```

Widgets connect to `bridge.scribe_output_ready` etc. (Qt's default
`AutoConnection` handles the cross-thread case correctly once the signal
is a real Qt signal) — **never** update a widget directly inside an
`EventHook` callback itself.

---

## 9. Phase 6 — `main.py` Wiring

- Add `--gui-qt` as a new flag, alongside the existing `--gui` (Tkinter,
  unchanged) and headless path. `--gui-qt` constructs `AllyCore`
  identically to the other paths (it already is GUI-agnostic — no
  changes needed there beyond §4.1's refactor), then constructs the prod
  overlay shell and starts `core.run_loop()` on a background thread, same
  pattern as the existing `--gui` branch.
- The dev window is **not** a separate CLI flag — per §7.5/§8, it's
  opened live from within the running `--gui-qt` app via the tray/icon
  action, never via a startup argument.
- Single-image back-compat mode (`args.image`) applies identically across
  all three launch modes — no changes needed to that branch.

---

## 10. Explicit Non-Goals for This Pass

Do not build any of the following — they were discussed and deliberately
deferred:

- Full settings-dialog parity (model overrides, thinking-level sliders,
  vision/threshold sliders, downscaling controls) — only the theme +
  personality pickers from §7.6.
- A real "Thinking" panel / thought-summary capture from Gemini.
- A global OS-level hotkey to summon the dev window.
- Deleting `gui/` (Tkinter) or the `--gui` flag.
- Desktop "buddy" mode (animated sprite companion) — a future, separate
  project phase with its own planning pass. The only thing this task
  should do in service of that future work is keep `EventHook`/`CoreBridge`
  generic enough that a third shell could subscribe the same way later —
  do not name anything `on_prod_x`/`on_dev_x`, keep hook names
  shell-agnostic (already reflected in the naming used throughout this
  doc).
- Full idle-peek/collapse animation polish (a functioning stub per §7.2
  is sufficient).

---

## 11. File Manifest

| Path | Action | Purpose |
|---|---|---|
| `utils/event_hook.py` | New | §4.1 |
| `ally/core.py` | Modify | Convert hooks to `EventHook`, add `on_ocr_result`/`on_scribe_output`/`on_ally_output`, add `turn_traces` |
| `logger/logger.py` | Modify | Pub/sub + `REGISTRY` expansion (§4.1) |
| `main.py` | Modify | Hook-assignment → `.connect()`; add `--gui-qt` (§4.1, §9) |
| `gui/tkinter_app.py` | Modify | Hook-assignment → `.connect()` only (§4.1) — no other changes |
| `state/turn_trace.py` | New | §4.2 |
| `state/entity_registry.py` | Modify | Add `name_lookup()` public method (§6.1) |
| `state/entity_highlighter.py` | New | §6.2 |
| `state/shell_bounds_registry.py` | New | §4.3 |
| `gui_qt/shell/capture_exclusion.py` | New | §4.3 |
| `collectors/screen_collector.py` | Modify | Blackout-mask fallback in `capture_bgr()` (§4.3) |
| `gui_qt/theming/theme.py` | New | §5.1–5.3 |
| `gui_qt/theming/base.qss.tmpl` | New | §5.4 |
| `gui_qt/theming/palette_hash.py` | New | §5.7 |
| `gui_qt/prod/message_formatting.py` | New | §6.3 |
| `gui_qt/prod/*` | New | §7 (window shell, feed panel, input bar, status strip, settings dialog) |
| `gui_qt/dev/*` | New | §8 (window shell, all dock panels, `CoreBridge`) |
| `docs/THEMING.md` | New | §5.6 |
| `requirements.txt` | Modify | Add `PySide6` |

---

## 12. Testing Expectations

Follow existing project convention: `unittest.TestCase` subclasses, not
bare pytest-style functions (see `tests/README.md`). Automated tests
first, manual smoke test for anything Qt-widget-heavy (consistent with
this project's existing "closures can't be exercised by unit tests
without refactoring" precedent for GUI-adjacent code).

Prioritize automated coverage for the parts with zero/minimal Qt
dependency, since these are cheap to test properly:

- `tests/test_event_hook.py` — connect/disconnect/emit, including that a
  raising subscriber doesn't prevent other subscribers from running.
- `tests/test_turn_trace.py` — ring buffer bound (`maxlen=20`) actually
  evicts oldest entries.
- `tests/test_entity_highlighter.py` — pure function, no Qt needed: exact
  match, alias match, longest-match-first (`"Marcus the Bold"` beats
  `"Marcus"`), case-insensitivity, `MIN_NAME_LENGTH` filtering, no false
  match on a substring of an unrelated word.
- `tests/test_palette_hash.py` — same key always returns the same color;
  stable across repeated calls within and across process runs (mock/
  verify it isn't using `hash()`).
- `tests/test_shell_bounds_registry.py` — update/unregister/all_bounds
  under concurrent access.

GUI widget behavior (drag/snap, dock layout persistence, rich-text
rendering) is manual-smoke-test territory, consistent with this
project's existing testing philosophy — do not force these into brittle
widget-simulation unit tests.

---

## 13. Notes for Claude's Code Review

**ZooCode: ignore this section entirely — it is not part of your task.**

When this comes back for review, specifically check:

- Every hook-assignment call site actually got converted to `.connect()`
  — this is the single easiest thing to miss/half-do, and a missed one
  will fail silently (no exception, the callback just never fires) rather
  than crash, so it won't necessarily show up in casual testing.
- Confirm no `EventHook` subscriber inside the Qt layer touches a widget
  directly without going through a `CoreBridge` — check especially the
  Entity Registry / Memory panels, since I specified those as poll-based
  (`QTimer`) rather than push-based specifically to sidestep this risk,
  and verify that pattern was actually followed rather than someone
  wiring a direct push subscription for convenience.
- Verify the entity-highlighter → Markdown-to-HTML ordering in
  `message_formatting.py` (§6.3, step 3) — confirm whether the
  `QTextDocument.setMarkdown()`/`.toHtml()` round-trip actually preserves
  inline `<span>` tags un-mangled, or whether the fallback to the
  `markdown` PyPI package was needed. If the PyPI package was pulled in,
  confirm it made it into `requirements.txt`.
- Confirm `SetWindowDisplayAffinity` was verified against the actual
  `mss`-based capture path in real testing, not just assumed to work —
  I flagged this as reasoned inference, not confirmed fact, in the
  original research.
- Confirm the blackout-mask fallback in `screen_collector.py` runs
  unconditionally (every capture) rather than being gated behind "only if
  `SetWindowDisplayAffinity` failed" — this was an explicit requirement,
  easy to accidentally implement as a conditional fallback instead.
- Spot-check that `color_for_key` is genuinely being used with `hashlib`,
  not Python's built-in `hash()` — an easy, silent, hard-to-notice-in-
  testing bug (works fine within one run, breaks on restart).
- Check whether `companion_palette` values got altered from the specified
  hex codes anywhere — I derived these transparently from existing
  assets (`OverlayConfig` defaults, `run.py`'s gradient) specifically so
  they'd be traceable; any deviation should have a stated reason.
