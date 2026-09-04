# Task: Unified Turn Timing Instrumentation + Timing Waterfall (Gantt-Style Chart)

## Context (read before starting)

`interfaces/gui_qt/dev/panels/timing_panel.py` is currently named "Timing
Waterfall" but is really just a flat `QTableWidget` of `(Turn, Stage,
Duration)` rows. It doesn't show *when* each stage started relative to the
turn, doesn't show stages overlapping or running back-to-back, and doesn't
give any visual sense of where a turn's time actually goes. This task
replaces it with a real waterfall/Gantt-style chart: one horizontal row per
turn, with each stage drawn as a bar positioned at its actual start offset
and sized to its actual duration.

**This task also resolves a real duplication problem uncovered while
scoping the chart work, and that problem must be fixed first, not worked
around.** The codebase currently has two independent, disconnected timing
mechanisms:

1. **`infrastructure/logger/logger.py`'s `@timed` decorator.** A live,
   ephemeral instrument: it pushes `time.perf_counter()` onto a
   thread-local stack keyed by the wrapped function's code object on entry,
   pops it on exit, and its only consumer (`resolve_module_info()`) uses it
   to compute "how long has the currently-executing timed call been
   running" so `log()` can print a `[N.NNNNNs]` annotation on a log line
   emitted from inside that call. **Nothing is retained after the function
   returns** — it cannot answer "how long did stage X take on turn 12"
   after the fact.
2. **Whatever currently populates `AllyCore.turn_traces`.** A separate,
   persisted mechanism inside `run_turn()` that manually calls
   `time.perf_counter()` at hand-picked stage boundaries and builds a
   `timings: dict[str, float]` per turn, which `TimingPanel` polls later.
   This is what the current (soon to be replaced) `QTableWidget` reads
   from. Critically, **it records durations only, with no start-offset
   data** — which is exactly what a real waterfall chart needs and what
   this mechanism cannot currently provide.

These two mechanisms are not guaranteed to agree, have no structural link
to each other, and a change to one has no reason to stay in sync with the
other. Building the waterfall chart on top of a *third*, newly-hand-rolled
timing mechanism inside `run_turn()` would make this worse, not better.
**Phase 1 below unifies these into one canonical timing source — an
extension of the existing `@timed` decorator — before any chart code is
written.** The chart (Phases 2–4) consumes that unified source.

This task is independent of
`CLAUDE_LED_TASK_dev_inspector_theming_and_views.md` but should still
**respect its outcomes** if that task has already landed by the time this
one starts: reuse the `theming/` package's `resolve_module_color()` for
per-stage bar coloring (see Phase 3.3) and the dev-inspector's active-theme
plumbing (`DevInspectorWindow._apply_active_theme()` /
`set_active_theme()` panel methods) rather than inventing a second,
parallel theming mechanism. If that task has **not** landed yet, hardcode
sensible colors as a stopgap (see Phase 3.3's fallback note) rather than
blocking this task on the other one.

**This task has 4 phases. Please subdivide into sub-tasks along these phase
boundaries** — Phase 1 in particular touches a pervasively-used piece of
shared infrastructure (the `@timed` decorator is applied across many
modules per `REGISTRY`) and deserves to be verified and landed cleanly
before any chart-specific code depends on it.

**Follow CLAUDE.md and `.markdownlint.yaml` conventions throughout**
(type hints, no `# type: ignore`, dataclasses over dicts, logger
`MODULE_NAME`/`REGISTRY` pattern, additive-over-modificatory).

---

## Phase 0 — Verification gates (mandatory, do this first)

### 0.1 — Confirm zero regression in existing `@timed` behavior before extending it

`@timed` is applied broadly today purely for live log annotation (the
`[N.NNNNNs]` prefix `log()` prints from inside a running decorated call).
Phase 1 extends this decorator's signature and internal behavior. Before
writing that extension:

1. Grep the codebase for every current `@timed` / `@timer` usage (both
   names refer to the same decorator — `timer = timed` in `logger.py`) and
   note each call site and how it's invoked (bare `@timed` vs. anything
   else — today it should only ever be bare, since it currently takes no
   arguments).
2. Confirm your planned signature change (Phase 1.1) is backward compatible
   with every one of these call sites without modifying them — i.e. bare
   `@timed` (no parentheses, no arguments) must continue to work exactly as
   it does today, unchanged, for every existing call site you just
   enumerated.
3. After implementing Phase 1.1, run the app (or at least exercise a code
   path that hits several `@timed` functions, e.g. a single-image turn) and
   confirm terminal log output's `[Ns]` annotations still appear correctly
   and with correct values, exactly as before this task.

**Bail-out condition:** if your planned decorator signature change cannot
cleanly support both the existing bare-decorator call sites and the new
opt-in tracing parameter, stop and report back rather than modifying every
existing `@timed` call site to adapt to a breaking signature change — that
would be a much larger blast radius than this task should have.

### 0.2 — Confirm `QtCharts` is actually importable and confirm the stacked-bar-as-Gantt technique works, live

`PySide6.QtCharts` ships from the `pyside6-addons` package
(`requirements.txt` already lists `pyside6-addons==6.11.1`), but this has
not actually been exercised anywhere in this codebase yet. Do not assume
the import works — verify it.

`QHorizontalBarSeries` alone cannot draw a bar that starts at a nonzero
offset (a "floating" bar) — every bar in a `QBarSeries`/`QHorizontalBarSeries`
starts at 0 by definition. The standard technique to fake a floating bar in
Qt Charts is a `QHorizontalStackedBarSeries` with **two `QBarSet`s per
visual bar**: the first ("offset") segment is rendered fully transparent and
represents the gap between 0 and the bar's real start time; the second
("duration") segment is the actual colored bar, stacked immediately after
the transparent one, so it visually appears to "float" starting at the
correct offset.

Before touching the real panel, write a small standalone throwaway Qt
script (or a diagnostic under `tooling/tools/`, your call) that:

1. Imports `PySide6.QtCharts` (`QChart, QChartView, QHorizontalStackedBarSeries,
   QBarSet, QBarCategoryAxis, QValueAxis`) and confirms the import succeeds
   in this environment.
2. Builds a minimal 2-row example: two "turns," each with two or three fake
   stages at different fake start offsets and durations, using the
   transparent-offset-segment + colored-duration-segment stacking technique
   described above.
3. Confirms visually (render it, or describe what you observe if you can't
   screenshot) that: (a) the transparent segment is genuinely invisible
   against the panel background, not just low-opacity, (b) the colored
   segment starts exactly where the offset segment ends, (c) hovering
   segments (if you enable `QBarSet.hovered` or similar) reports sensible
   values, since Phase 3's tooltip requirement depends on this working.

**Bail-out condition:** if `QtCharts` fails to import at all in this
environment, or if the transparent-segment technique produces visible
artifacts (a seam, a border, a color bleed) that can't be cleanly resolved
via `QBarSet.setBorderColor(Qt.transparent)` / similar, **stop and report
back** rather than shipping a visually broken chart or silently falling
back to a different charting approach on your own. This is a genuine
scope-affecting risk, not a routine implementation detail — treat it as one.

---

## Phase 1 — Unified turn timing instrumentation

This phase makes `@timed` the single source of truth for both the
terminal's live elapsed-time log annotation (existing behavior, unchanged)
and the waterfall chart's structured per-turn stage data (new). The
hand-rolled `timings: dict[str, float]` mechanism currently feeding
`turn_traces` is replaced by this, not left running alongside it.

### 1.1 — Extend `@timed` with an opt-in tracing marker

In `infrastructure/logger/logger.py`, change `timed` from a plain decorator
into a decorator *factory* that still supports bare usage:

```python
def timed(func: Callable | None = None, *, trace_as: str | None = None) -> Callable:
    """Decorator to track function execution time seamlessly with the tree
    logger, and optionally record it as a named stage in the current
    thread's active turn trace (see turn_trace_context below).

    Bare usage (@timed, no parentheses/arguments) behaves exactly as
    before -- pushes/pops a thread-local timing stack entry purely for
    resolve_module_info()'s live elapsed-time log annotation.

    @timed(trace_as="scribe_call") additionally appends a
    (stage_name, start_offset_seconds, duration_seconds) entry to the
    thread-local active TurnTrace, if one is currently open (see
    turn_trace_context) -- a no-op if no trace is currently active, so
    a trace_as-marked function called outside of a turn_trace_context
    block behaves exactly like bare @timed.
    """
```

Implementation notes:

- Support both `@timed` (bare, `func` positional, `trace_as=None`) and
  `@timed(trace_as="...")` (called with no positional `func`, returns the
  actual decorator) — the standard "decorator that can be used with or
  without arguments" pattern. Get this exactly right and verify both forms
  work, since Phase 0.1 depends on it.
- The existing thread-local stack (`_timing_storage`/`_get_timing_stack()`)
  stays exactly as-is for the live-annotation purpose — do not remove or
  restructure it, only add to what happens around it.
- Add a **second, separate thread-local**: the "active turn trace." When a
  `trace_as`-marked function is entered, if an active trace exists for the
  current thread, compute `start_offset = time.perf_counter() -
  active_trace.turn_start_time` before calling the wrapped function, then
  on successful return (or in a `finally`, so a raised exception still
  records partial timing rather than losing the entry — use your judgment
  on whether a failed stage should still appear on the chart, but lean
  toward recording it, since a stage that failed after 4 seconds is
  valuable waterfall information, not noise to hide) compute
  `duration = time.perf_counter() - stage_start_perf_counter` and append
  `StageBar(stage_name=trace_as, start_offset_seconds=start_offset,
  duration_seconds=duration)` to `active_trace.stages`.

### 1.2 — `TurnTrace` / `StageBar` dataclasses and the trace-context manager

Add to `infrastructure/logger/logger.py` (or a new small adjacent module if
you judge `logger.py` is getting crowded — your call, but keep it under
`infrastructure/logger/` since this is genuinely an extension of the
logger's timing responsibility, not a separate concern):

```python
@dataclass
class StageBar:
    stage_name: str
    start_offset_seconds: float
    duration_seconds: float

@dataclass
class TurnTrace:
    turn: int
    turn_start_time: float  # time.perf_counter() at open_turn_trace() call
    stages: list[StageBar] = field(default_factory=list)


def open_turn_trace(turn: int) -> None:
    """Opens a new active TurnTrace for the current thread, capturing
    time.perf_counter() as this turn's start reference. Any trace_as-marked
    @timed call on this thread between this call and close_turn_trace()
    will append a StageBar to it.
    """

def close_turn_trace() -> TurnTrace | None:
    """Closes and returns the current thread's active TurnTrace (or None
    if none was open), clearing the thread-local so a subsequent turn
    starts clean.
    """
```

Thread-local storage for the active trace, parallel to the existing
`_timing_storage` pattern (`threading.local()`), not reusing the same
thread-local object as the elapsed-time stack — keep these two concerns
structurally separate even though they're both timing-related, since one
is a stack (nested calls) and the other is a flat list keyed to a turn
boundary.

### 1.3 — Wire into `run_turn()`

Locate `run_turn()` in `brain/reasoning/core.py` (per `ARCHITECTURE.md`,
this is where `AllyCore` drives one full pipeline pass) and:

1. Call `open_turn_trace(turn=<current turn number>)` at the very top,
   before any pipeline stage begins.
2. Add `trace_as="..."` to the `@timed` decorator on each pipeline-stage
   function/method you want represented on the waterfall — at minimum the
   stages `ARCHITECTURE.md`'s pipeline diagram names: Scribe call, OCR
   read, Ally call, memory flush/record — using clear, stable names (these
   names become both the chart's stage labels and, if
   `CLAUDE_LED_TASK_dev_inspector_theming_and_views.md` has landed, the
   keys `resolve_module_color()` looks up against `REGISTRY` display
   names — prefer matching existing `REGISTRY` display names exactly,
   e.g. `"Scribe"`, `"AllyCore"`, rather than inventing new snake_case
   stage identifiers, so the color-consistency goal in Phase 3.3 actually
   works without a second mapping table).
   If a stage you want traced isn't already wrapped in `@timed` at all,
   add it — don't leave a pipeline stage untimed just because it wasn't
   instrumented before.
3. At the end of `run_turn()` (success and failure paths both — use
   `try`/`finally`), call `close_turn_trace()` and append the resulting
   `TurnTrace` to `AllyCore.turn_traces`, replacing whatever currently
   builds and appends the old `timings: dict[str, float]`-shaped entry
   there. **Remove the old hand-rolled timing-capture code** in
   `run_turn()` entirely — this is a full replacement of that mechanism,
   not an additive second one living alongside it.
4. Check whether anything other than `TimingPanel` reads `turn_traces` or
   the shape of its entries (grep for `turn_traces` and for `.timings`
   usage) and update any other caller to the new `TurnTrace`/`StageBar`
   shape. If `TimingPanel` turns out to be the only consumer, this is
   simple; if not, treat updating the others as in-scope for this phase,
   not something to discover later.

### Phase 1 — verification / definition of done

- Existing bare `@timed` call sites are provably unaffected (Phase 0.1's
  check, re-run after implementation).
- A single real turn produces a `TurnTrace` with correct `stages` — verify
  by hand: run one turn, dump the resulting `TurnTrace`, and confirm each
  `StageBar`'s offset and duration look sane relative to when you'd expect
  each stage to actually run (e.g. Scribe's offset should be small/near
  zero if it's early in the pipeline; memory flush's offset should be
  larger).
- The old `timings: dict[str, float]` mechanism inside `run_turn()` is
  fully removed, not left dormant alongside the new one.
- `AllyCore.turn_traces` now holds `TurnTrace` objects; every other reader
  of `turn_traces` (if any exist beyond `TimingPanel`) has been updated
  accordingly.

---

## Phase 2 — Panel-side data transformation

With Phase 1 in place, `TurnTrace`/`StageBar` already carry exactly the
shape the chart needs — this phase is now much lighter than it would have
been without Phase 1, since there's no offset math left to invent at the
panel level.

In the new/rewritten panel (Phase 3), each poll cycle:

- Read `core.turn_traces` (a `list[TurnTrace]`).
- Sort each `TurnTrace.stages` by `start_offset_seconds` ascending (should
  already be in this order given append-on-completion in Phase 1.1, but
  don't rely on that ordering being guaranteed — sort defensively).
- Compute each turn's total duration as
  `max(s.start_offset_seconds + s.duration_seconds for s in trace.stages)`
  (or `0.0` for a trace with no stages, defensively).
- Cap the number of turns displayed at once to something reasonable (e.g.
  the most recent 20 turns) so the chart doesn't become unusably tall or
  slow over a long play session — this mirrors the existing `_log_tail`
  cap-at-5 pattern used elsewhere in the dev inspector, just at a larger
  number appropriate for a chart rather than a text tail.

No new dataclasses are needed here beyond what Phase 1 already defined —
if you find yourself wanting to reshape `TurnTrace`/`StageBar` further at
the panel level, prefer adjusting Phase 1's dataclasses themselves so
there's still exactly one shape for this data, not a second
panel-local transformation of it.

---

## Phase 3 — The chart itself

### 3.1 — Chart structure

Replace `TimingPanel`'s `QTableWidget` with a `QChartView` embedding a
`QChart` containing one `QHorizontalStackedBarSeries`.

- **Category axis (Y, vertical list of categories despite this being a
  horizontal bar chart — Qt Charts' naming convention)**: one category per
  turn, labeled e.g. `"Turn 12"`. Use `QBarCategoryAxis`.
- **Value axis (X, time in seconds)**: `QValueAxis`, ranging from 0 to the
  max total duration across all currently displayed turns (from Phase 2),
  recomputed each poll cycle so the axis rescales as slower/faster turns
  come and go — do not hardcode a fixed max.
- **Bar sets**: for each *distinct stage name* seen across all displayed
  turns (the `trace_as` names from Phase 1.3, e.g. `"Scribe"`, `"AllyCore"`,
  `"LayoutOCRReader"`, `"MemoryManager"`), you need **two `QBarSet`s**: one
  transparent "offset" set and one colored "duration" set, per the Phase
  0.2-verified technique. Since different turns can have different stages
  present (a skipped-Scribe turn has fewer stages than a full turn — see
  `ARCHITECTURE.md`'s `skip_ally` semantic diff guard), missing stages for
  a given turn should contribute `0.0` to that stage's offset-set and
  duration-set values for that turn's category slot, not be omitted —
  `QBarSet` values must align positionally with categories.
- Because `QHorizontalStackedBarSeries` stacks *all* bar sets added to it
  in insertion order, the correct construction order per stage is:
  `series.append(offset_set_for_stage)` immediately followed by
  `series.append(duration_set_for_stage)`, and this offset/duration pair
  ordering must be repeated per stage, in a **consistent stage order across
  all turns** — otherwise the stacking order becomes inconsistent between
  turns and the chart will misrepresent adjacency. Use pipeline order (per
  `ARCHITECTURE.md`'s diagram: Scribe → OCR → Ally → memory) as the fixed
  ordering, determined once and held fixed for the panel's lifetime, only
  extending it (never reordering) if a genuinely new stage name appears
  mid-session. **Do not derive this ordering from dict/set iteration order**
  of whatever turn happened to be processed first — Python's insertion-order
  preservation is easy to mistake for "a fixed, intentional order" when
  it isn't guaranteed to be the same across turns with different stage
  subsets; define the ordering as an explicit list.

### 3.2 — Transparent offset segments

- Every "offset" `QBarSet`: `set_.setColor(Qt.GlobalColor.transparent)`,
  `set_.setBorderColor(Qt.GlobalColor.transparent)` (per Phase 0.2's
  verification — border must also be transparent or a visible seam
  appears), and exclude it from the legend
  (`chart.legend()->markers(offset_set)` → hide each marker, or simpler:
  build the legend manually from only the duration sets — check which is
  cleaner once you're in the API).

### 3.3 — Stage bar coloring

- If `CLAUDE_LED_TASK_dev_inspector_theming_and_views.md` has already
  landed: color each stage's "duration" `QBarSet` using
  `theming.palettes.resolve_module_color(active_theme_name, stage_name)`
  — since Phase 1.3 instructed using `REGISTRY` display names as
  `trace_as` values, this should resolve directly with no extra mapping
  table, keeping this chart's stage colors visually consistent with that
  same stage's color in the log panel and everywhere else in the dev
  inspector. Add a `set_active_theme(theme_name: str)` method to this
  panel too, called by `DevInspectorWindow._apply_active_theme()`, that
  rebuilds the chart's bar colors (not the whole chart — just re-set each
  `QBarSet`'s color) when the theme changes.
- If that task has **not** landed yet: hardcode a small fixed list of
  distinct, visually distinguishable colors (reuse the exact hex list
  already used for `Theme.companion_palette` on `SIGNAL`, e.g. `["#ff9900",
  "#aa88ff", "#00cc77", "#c93b55", "#ffd966", "#00ffff", "#00ffcc"]`) and
  assign them to stages in the fixed pipeline order from §3.1, cycling if
  more stages than colors exist. Leave a `# TODO` comment noting this
  should be replaced with `theming.palettes.resolve_module_color()` once
  that package exists, so it's easy to find and wire up later rather than
  forgotten.

### 3.4 — Tooltips

- Enable hover tooltips on each duration `QBarSet` (`QBarSet.hovered`
  signal) showing at minimum: stage name, start offset (formatted as
  `"{:.3f}s"`), duration (`"{:.3f}s"`). This is exactly what Phase 0.2's
  verification step should have already confirmed works cleanly with the
  stacked-transparent-segment technique — if it turned out to be flaky
  there, it will be flaky here too; don't discover that for the first time
  in the real panel.

### 3.5 — Polling / refresh

- Keep the existing `QTimer`-based poll pattern (`_poll_timings()` on a
  ~1000ms interval, matching the current panel's cadence) rather than
  wiring this to a push-based signal — this is consistent with how
  `EntityPanel`/`MemoryPanel` already poll rather than subscribe, and
  changing that pattern is out of scope here. This `QTimer` is purely a UI
  refresh cadence — it has no bearing on the actual timing measurements,
  which now come entirely from Phase 1's `TurnTrace` mechanism.
- On each poll: rebuild the displayed turn set (Phase 2), and update the
  chart's series/categories/axis range. **Do not fully destroy and
  recreate the `QChart` object every poll** if avoidable — Qt Charts
  supports updating `QBarSet` values in place
  (`bar_set.replace(index, new_value)` or similar) and updating axis
  ranges without rebuilding the whole chart; investigate the cleanest way
  to do an in-place update during Phase 0's exploration, since a full
  rebuild every second is likely to cause visible flicker.

### Phase 3 — verification / definition of done

- Chart shows one row per turn, each with correctly positioned/sized bars
  per stage — verified by comparing at least one real turn's rendered bars
  against that turn's actual `TurnTrace.stages` values by hand.
- No visible seam/artifact from the transparent offset segments.
- Tooltips report correct stage name/offset/duration on hover.
- Chart updates live during a running session without flicker or a
  perceptible rebuild stutter.
- Stage bar colors are visually consistent across turns (same stage always
  same color) and, if the theming task has landed, consistent with that
  stage's color elsewhere in the dev inspector.

---

## Phase 4 — Panel integration and cleanup

- Rename the panel class if appropriate (`TimingPanel` can stay as the
  class name — the dock widget title is already "Timing Waterfall," which
  is now finally accurate — but update the module docstring at the top of
  `timing_panel.py`, which currently says "rendering turn stage timings" in
  a way that undersells what it now does).
- Remove the old `QTableWidget`-based rendering path entirely (this is a
  full replacement, not an additive alternate view — a table and a Gantt
  chart showing the same data side by side would just be visual clutter in
  an already dense dev inspector).
- Confirm `DevInspectorWindow._setup_docks()`'s existing wiring for the
  Timing dock (`self._timing_panel = TimingPanel(self._core, self)`, added
  via `QtAds.DockWidgetArea.BottomDockWidgetArea`) still works unmodified —
  this task should not need to touch dock registration, only the panel's
  internals.
- If the theming task's `set_active_theme()` panel convention exists by the
  time this lands, confirm `DevInspectorWindow.set_core()` /
  `_apply_active_theme()` actually calls this panel's `set_active_theme()`
  too (it will need to be added to whichever loop/list of panels that
  method iterates over) — an easy panel to forget since it wasn't in the
  original theming task's file list.

---

## Documentation updates (required — do not skip)

1. **`docs/changelog.md`** — routine entry covering: the `@timed`
   decorator's new `trace_as` parameter and its backward-compatibility
   guarantee, the new `TurnTrace`/`StageBar` dataclasses and where they
   live, removal of the old hand-rolled `timings` dict mechanism inside
   `run_turn()`, the panel replacement itself, the color decision actually
   taken (§3.3), and the turn-count display cap chosen (§2).
2. **`docs/ally_decision_log.md`** — this task resolved a genuine
   duplication problem (two disconnected timing mechanisms) by unifying
   onto one, and separately made a real architectural choice about how to
   render a floating Gantt bar in Qt Charts. Both deserve entries:
   - **Unified timing instrumentation**: why `@timed` was extended rather
     than building a separate turn-timing mechanism, why it's backward
     compatible (bare `@timed` unaffected), and that the old
     `run_turn()`-local `timings` dict was fully removed rather than left
     running alongside the new mechanism.
   - **Transparent-stacked-bar Gantt technique**: why this shape rather
     than a different charting library or a custom-painted `QWidget`,
     since a future reader staring at "why are there two QBarSets per
     stage" deserves the answer without having to re-derive it.
3. **`docs/roadmap.md`** — if the turn-count display cap (§2) or the
   hardcoded-color fallback (§3.3, only if the theming task hadn't landed
   yet) represents something worth revisiting later, add it here rather
   than leaving it silently baked in. Also worth noting here (not fixing
   now): whether other consumers might eventually want `trace_as` on more
   `@timed` call sites beyond the pipeline stages covered in this pass.

---

## Notes for Claude's code review (ZooCode: ignore this section — it is not part of your task)

Things to specifically check when this comes back:

- Confirm bare `@timed` really is provably unaffected — I want to see
  Phase 0.1's before/after comparison actually happened, not assumed.
  Check a couple of non-pipeline `@timed` call sites (e.g.
  `config_manager.py`, `event_hook.py`) still produce correct `[Ns]`
  terminal annotations.
- Confirm the old `timings: dict[str, float]` mechanism was actually
  *removed* from `run_turn()`, not left in place alongside the new
  `TurnTrace` mechanism "just in case" — that would silently reintroduce
  the exact duplication this task exists to eliminate.
- Check whether `trace_as` stage names actually match `REGISTRY` display
  names exactly, as instructed in Phase 1.3 — a mismatch here would break
  Phase 3.3's color-consistency goal silently (colors would still render,
  just inconsistently with the rest of the dev inspector, which is an easy
  thing to not notice without specifically comparing).
- Verify the fixed stage ordering (§3.1) is actually a fixed, explicit list
  and not accidentally derived from dict/set iteration order of whatever
  turn happened to be processed first.
- Confirm the poll-and-update path (§3.5) is genuinely doing in-place
  `QChart` updates and not secretly doing
  `chart.removeAllSeries(); # rebuild everything` every second, which is
  the easy-but-wrong way to satisfy "the chart updates live" without
  actually solving the flicker/perf concern.
- Actually verify both Phase 0 bail-out conditions weren't quietly worked
  around — if either the decorator signature change or the QtCharts
  transparent-segment technique had real trouble, I want to see that
  reported, not papered over with an approximate fix that still looks
  slightly wrong at certain window sizes or under certain call patterns.
- Confirm the old `QTableWidget` path (Phase 4) was fully removed, not left
  dead in the file alongside the new chart — this is one of the rare cases
  in this codebase where the usual additive-over-modificatory convention
  correctly does not apply, and it'd be easy for that reflex to kick in
  anyway and leave cruft behind.
- Check whether any other code beyond `TimingPanel` read the old
  `turn_traces` shape (Phase 1.3, step 4) and, if so, whether it was
  actually updated rather than silently left broken.
