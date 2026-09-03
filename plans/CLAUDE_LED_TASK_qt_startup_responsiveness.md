# Task: Diagnose and Fix Qt GUI Startup Responsiveness

**Status:** Ready for ZooCode
**Author:** Claude (architecture/spec), for Ficus
**Scope:** `run.py`, `main.py`, `interfaces/visuals/header.py`, `gui_qt/prod/overlay_window.py`
(and any files those two pull in at *module level*), plus a small, targeted look at
`brain/reasoning/core.py`'s `AllyCore.__init__`/`initialize_run()`.

**Non-goals (explicit scope boundaries):**
- Do **not** touch thread-locking, `state_lock`, `EventHook`, `MemoryDB`, or any of the
  concurrency work described in `docs/changelog.md`'s "Concurrency & Thread Safety
  Implementation" entry. That pass is considered settled; this task is purely about
  *startup sequencing and import ordering*, not correctness under concurrent access.
- Do **not** change what gets loaded (no removing/deferring actual features like CLIP,
  TTS, MTGA, etc.) — only *when* and *on which thread* the code that loads them runs.
- Do **not** change GUI visual design, layout, or theming.
- If a fix under consideration would require changing business logic (e.g. reordering
  `AllyCore.initialize_run()`'s actual initialization *sequence*, not just *which thread
  it runs on*), stop and flag it in your report instead of doing it — that's a design
  call for Claude/Ficus, not something to decide unilaterally.

---

## 1. Context

Three related problems were reported, in increasing order of severity:

1. **Minor:** There is a noticeable delay before the Qt GUI feels "live," even though
   `QApplication`/`ProdOverlayWindow` construction was already moved to the earliest
   possible point in the startup sequence in a prior pass. It's unclear how much of this
   is unavoidable PySide6/Python import cost vs. something fixable.
2. **Minor but concrete:** This terminal line is provably wrong —
   `[Run][initialize_and_run][3.88086s] GUI displayed successfully, starting core
   pipeline initialization...` — it prints *before* the window has actually rendered
   on screen, not after.
3. **Major:** The GUI is unresponsive (won't even process a window-drag) for a
   noticeable period during startup, up until roughly when `AllyCore` finishes being
   instantiated. Moving `AllyCore` construction earlier in the load order helped, but
   did not fully solve it.

Item 3 is the one that actually matters to the player experience; items 1–2 are
diagnostic breadcrumbs that point at the same root cause. Treat them as one
investigation, not three separate bugs.

## 2. Confirmed facts (from the person's own logs — don't re-derive these, just use them)

```text
[Run][initialize_and_run][3.88086s] GUI displayed successfully, starting core pipeline initialization...
[CategoryStore][__init__]        Initializing ScreenCategoryStore...
[CategoryStore][_ensure_seeded][0.00163s] Screen categories already seeded.
[Main][_async_init]              AllyCore instantiated. Calling initialize_run()...
[AllyCore][initialize_run]       Initializing run in AllyCore...
```

The `[3.88086s]` figure comes from `initialize_and_run`'s own `@timer` decorator (see
`infrastructure/logger/logger.py`'s `timed`/`resolve_module_info` — the bracketed
number is elapsed time *since that specific function was entered*). That means **3.88
seconds elapse inside `initialize_and_run` itself**, before it even calls
`main_module.run_qt_app_with_overlay(app, overlay)` — i.e. before `AllyCore` is anywhere
in the picture. Whatever is costing 3.88s is happening in:

- `PySide6.QtWidgets.QApplication` import/construction, or
- `gui_qt.prod.overlay_window` import (module-level statements run once, at first
  import), or
- `ProdOverlayWindow(registry=None)`'s constructor body, or
- `overlay.show()` / `overlay.add_ally_message(...)`.

This number does **not** include whatever `run_header_splash()` (called in `run.py`'s
`main()`, *before* `initialize_and_run`) itself costs — that's currently untimed and
invisible in the log. The real total delay before the window is responsive could be
larger than 3.88s.

**Claude does not have the source of `interfaces/visuals/header.py` or
`gui_qt/prod/overlay_window.py`.** Everything below involving those two files is a
hypothesis to be confirmed or refuted in Phase 0, not an assumption to build on
directly.

## 3. Working hypotheses (rank-ordered, to be confirmed in Phase 0)

1. **(High confidence, confirmed by reading the provided source)** In
   `main.py`'s `run_qt_app_with_overlay()`, these imports run at the *top of the
   function*, synchronously, on the main thread, **before `app.exec()` is called**:

   ```python
   from PySide6.QtCore import QTimer
   from gui_qt.dev.dev_window import DevInspectorWindow
   from gui_qt.dev.bridge import CoreBridge
   from brain.reasoning.core import AllyCore
   from ingestion.collectors.base import RawObservation
   from PIL import Image
   ```

   `from brain.reasoning.core import AllyCore` alone pulls in an enormous transitive
   import graph: `cv2`, `numpy`, `PIL`, `pytesseract`, `scikit-image`, `fastembed`
   (conditionally), `google.genai`, every `brain.memory.*`/`brain.state.*`/
   `brain.perception.*`/`brain.reasoning.*` module, `pydantic` schemas, etc. Because
   `app.exec()` is the *last* line of `run_qt_app_with_overlay()`, **the Qt event loop
   cannot start — and the already-`show()`n window cannot actually paint or process any
   input event, including a drag — until all of that import machinery finishes running
   on the main thread.** This is very likely the dominant cause of item 3 (the "freeze
   until AllyCore is instantiated" — really, "freeze until AllyCore's *module* finishes
   importing," which is a superset of instantiation time).

   This also explains item 2: the `log("GUI displayed successfully...")` call happens
   in `run.py`, chronologically *before* `run_qt_app_with_overlay()` is even called, so
   it's printed well before `app.exec()` ever runs, which is the only thing that
   actually causes the window to paint.

2. **(Unconfirmed — needs Phase 0)** `gui_qt/prod/overlay_window.py` and/or
   `interfaces/visuals/header.py` may themselves import something heavy at module
   level, which would explain the 3.88s figure landing *before* `run_qt_app_with_overlay`
   is ever reached. `run.py`'s own module docstring states the intended principle
   explicitly: *"Instantiate and show QApplication and ProdOverlayWindow at absolute
   earliest point, before importing heavy perception/core modules or loading
   configurations/models."* If either file violates that principle, it's a bug against
   the project's own stated design intent, not a new problem to solve from scratch.

3. **(Lower priority, secondary contributor)** Once `_async_init()` genuinely runs on a
   background thread (post-fix for hypothesis 1), CPython's GIL still means CPU-bound
   pure-Python work in that thread (bytecode execution during imports, JSON/sqlite
   glue code, etc.) competes with the main/UI thread for scheduling. This can cause
   residual stutter (not a full freeze) even after hypothesis 1 is fixed, especially
   with a *third* thread (`ClipModelLoader`, spawned from inside `ClipClassifier.__init__`,
   which itself runs inside `AllyCore.__init__`, which itself runs inside `_async_init`)
   also competing for the GIL concurrently.

## 4. Phase 0 — Instrumentation & Diagnosis (mandatory, gates Phase 1)

**Do not skip to Phase 1 based on the hypotheses above.** They are informed guesses,
not confirmed findings. Phase 0's job is to turn them into facts.

### 4.1 Files to read in full before changing anything

- `interfaces/visuals/header.py`
- `gui_qt/prod/overlay_window.py`
- Any module either of the above imports at its own top level (follow the chain one
  level deep — you don't need to audit the entire codebase, just confirm whether either
  file pulls in anything from `brain/`, `ingestion/`, `infrastructure/llm/`,
  `infrastructure/tts/`, `infrastructure/stt/`, `cv2`, `numpy`, `PIL`, `google.genai`,
  `fastembed`, or `scikit-image` **at module level** — i.e. outside of a function body).

Report what you find, even if it contradicts hypothesis 2 above (e.g. "confirmed: both
files are already lazy-import-clean, the 3.88s is entirely `QApplication`/
`ProdOverlayWindow.__init__` cost" is a valid and useful finding).

### 4.2 Instrumentation to add

All timing output should go through the existing `log()` / `@timed` conventions
already used throughout this codebase (see `infrastructure/logger/logger.py`) — don't
invent a parallel logging mechanism. `@timed` gives you a clean `[elapsed]` figure for
free via the existing `REGISTRY`/`resolve_module_info` machinery; use plain
`time.perf_counter()` deltas + explicit `log(...)` calls only where `@timed` doesn't
fit (e.g. timing a chunk of a function rather than the whole function, or timing a
bare import statement).

Add the following, in order of where they sit on the startup timeline:

1. **`run.py`'s `main()`**: wrap the `run_header_splash()` call with explicit
   `time.perf_counter()` before/after and a `log(...)` reporting the elapsed time. This
   function currently runs with zero visibility into its cost.

2. **`interfaces/visuals/header.py`**: if `run_header_splash()` is a plain function (not
   already `@timed`), add `@timed` to it (check the file's own `MODULE_NAME` global or
   whether `header.py` is in `logger.py`'s `REGISTRY` dict already — if not, either add
   an entry there matching the existing convention, e.g.
   `"header.py": {"name": "HeaderSplash", "color": "<pick an unused color from
   infrastructure/logger/logger.py's COLORS dict>"}`, or pass `name=` explicitly to
   `log()` calls). If this function does any of its own heavy imports or blocking work
   (e.g. showing a splash `QWidget`/`QApplication` synchronously, loading an image
   asset, etc.), add timing around each distinct sub-step, not just the function as a
   whole — the goal is to be able to point at *one specific line* as the culprit, not
   just "this function is slow."

3. **`gui_qt/prod/overlay_window.py`**: add `@timed` to `ProdOverlayWindow.__init__` if
   it isn't already decorated (it's already registered in `logger.py`'s `REGISTRY` as
   `"overlay_window.py": {"name": "ProdOverlay", ...}`, so this should be a one-line
   addition). If `__init__` does any distinctly heavy sub-step (loading a stylesheet,
   constructing many child widgets, loading fonts/icons, etc.), add inline timing
   around those sub-steps too, same reasoning as above.

4. **`run.py`'s `initialize_and_run()`**: it's already `@timer`-decorated, so the
   existing `[3.88086s]`-style figure at the "GUI displayed successfully" log line is
   already useful — but *only* once steps 1–3 above exist to explain what happened
   *before* that line. Leave this decorator as-is for now (it gets touched again in
   Phase 2).

5. **`main.py`'s `run_qt_app_with_overlay()`**: add explicit `time.perf_counter()`
   timing around the block of top-of-function imports (`DevInspectorWindow`,
   `CoreBridge`, `AllyCore`, `RawObservation`, `Image`) as a single group, with a `log(...)`
   reporting total import time for that block. This is the number that (per hypothesis 1)
   should turn out to be large and should be blocking `app.exec()`.

6. **`brain/reasoning/core.py`'s `AllyCore.__init__`**: add `@timed` (it isn't currently
   decorated — only `run_turn`/`run_loop` are). This isolates `AllyCore()` construction
   time from `initialize_run()`'s time, which the current log already separates at the
   *log-statement* level but not at the *timing* level.

7. **`brain/reasoning/core.py`'s `AllyCore.initialize_run()`**: add fine-grained timing
   around each of: `build_collector(...)`, `MemoryManager(...)` construction, and
   `EntityRegistry(...)` construction (the non-image-path branch — that's the one that
   actually runs in this project's normal launch mode). Use the same
   `time.perf_counter()` + `log(...)` pattern as elsewhere in this file (see
   `run_turn()`'s existing `timings: dict[str, float]` pattern for a style to match,
   though you don't need to build a full `dict` here — simple sequential `log()` calls
   are fine for a diagnostic pass).

### 4.3 Running and capturing

Launch the app the same way it's normally launched (`python run.py`, no `--headless`/
`--gui` flags, so the PySide6 path in `run.py`'s `initialize_and_run()` is exercised).
Let it fully reach the point where `AllyCore.initialize_run()` completes and the
overlay is fully interactive. Capture the **complete** terminal output from process
start through that point (the `logs/ally_<timestamp>.log` file this project already
writes to disk is the easiest way to get a clean copy — see `infrastructure/logger/logger.py`'s
`LOG_FILE` handling).

### 4.4 Deliverable

Append a new dated entry to `docs/changelog.md` (this is a diagnostic/implementation
pass, not a design-rationale decision, so `docs/changelog.md` is the right home per
`CLAUDE.md`'s doc map — **not** `docs/ally_decision_log.md`). Include:

- The full captured timing breakdown (a simple ordered list of step → elapsed seconds
  is fine, doesn't need to be fancy).
- An explicit statement of which hypothesis from §3 was confirmed, refuted, or
  partially confirmed, with the evidence.
- If something unexpected turned up that isn't covered by any hypothesis above,
  describe it plainly — don't force it into one of the existing buckets.

**Bail-out condition:** if the Phase 0 findings substantially contradict hypothesis 1
(e.g. it turns out `run_qt_app_with_overlay`'s heavy imports are *not* meaningfully
blocking `app.exec()`, and the real cost is somewhere Phase 1 below doesn't address),
stop, write up the findings as described above, and do not attempt to freelance a new
fix — that's a case for another round of specification, not something to improvise.

## 5. Phase 1 — Fix: get to `app.exec()` before doing heavy imports

Assuming Phase 0 confirms hypothesis 1 (expected, based on direct code reading), apply
this fix to `main.py`'s `run_qt_app_with_overlay()`:

Move the following imports **out of the top of `run_qt_app_with_overlay()`** and into
the specific nested function that actually uses them:

- `from brain.reasoning.core import AllyCore` → into `_async_init()` (the only place
  `AllyCore(...)` is constructed).
- `from ingestion.collectors.base import RawObservation` and `from PIL import Image` →
  into `_async_init()` as well (they're only used inside `_run_single()`, which is
  itself only defined/called from within `_on_core_initialized`, which is only reached
  after `_async_init` completes — but importing them at the top of `_async_init` is
  simplest and keeps them close to their one call site; either placement is fine as
  long as they're off the pre-`app.exec()` path).
- `from gui_qt.dev.dev_window import DevInspectorWindow` and
  `from gui_qt.dev.bridge import CoreBridge` → into `_on_core_initialized()`, the only
  place either is used.
- `from PySide6.QtCore import QTimer` stays at the top of `run_qt_app_with_overlay()` —
  it's needed immediately (for the `QTimer.singleShot(50, ...)` call near the bottom of
  the function) and it's cheap (`PySide6.QtCore` is already loaded as part of
  `PySide6.QtWidgets` by this point).

After this change, `run_qt_app_with_overlay()`'s only work before `app.exec()` should
be: defining the nested functions (`_on_core_initialized`, `_async_init`) and the
`QTimer.singleShot(50, overlay, lambda: threading.Thread(target=_async_init,
daemon=True).start())` call. None of that does meaningful import or CPU work, so
`app.exec()` should be reached almost immediately, letting the event loop start
processing paint/input events right away.

**Verify no circular imports or scoping issues result.** `AllyCore`, `RawObservation`,
`Image`, `DevInspectorWindow`, and `CoreBridge` are currently referenced inside
closures (`_async_init`, `_on_core_initialized`, and nested functions within them like
`_run_single`) that already capture other outer-scope names (like `args`, `core_holder`,
`overlay`) — moving the imports into the same function bodies that use them should work
cleanly with Python's normal closure/scoping rules, but confirm this by actually running
the app end-to-end after the change, not just by reading the diff.

## 6. Phase 2 — Fix: make the "GUI displayed" log line actually true

In `run.py`'s `initialize_and_run()`, this block:

```python
overlay.show()
overlay.add_ally_message("System", "Initializing Ally & Perception pipeline...")

log("GUI displayed successfully, starting core pipeline initialization...", level="info")

main_module.run_qt_app_with_overlay(app, overlay)
```

Replace the immediate `log(...)` call with one deferred via `QTimer.singleShot(0, ...)`,
so it only actually prints once control returns to the Qt event loop (i.e. after
`app.exec()` begins running inside `run_qt_app_with_overlay`), rather than printing
synchronously on the same line it's currently on. Concretely:

```python
from PySide6.QtCore import QTimer  # add this import alongside the existing QApplication import

# ... existing overlay.show() / add_ally_message() calls unchanged ...

QTimer.singleShot(0, lambda: log(
    "GUI event loop running, starting core pipeline initialization...",
    level="info",
))

main_module.run_qt_app_with_overlay(app, overlay)
```

Note the reworded message ("GUI event loop running..." rather than "GUI displayed
successfully...") — a 0ms singleShot firing on the first event-loop iteration is a much
closer approximation of "the loop has started and can now paint/respond" than the old
synchronous call was, but it's still not a hard guarantee that the very first paint has
already completed by that exact instant, so don't overclaim in the message text.

This works whether or not `run_qt_app_with_overlay` itself still does the pre-`app.exec()`
work described in Phase 1 — `QTimer.singleShot` just queues the timer; it fires once
`app.exec()` actually starts running the loop, whenever that ends up being. Applying
both Phase 1 and Phase 2 together means the log line should now print almost
immediately, right as the window becomes genuinely interactive — which is the whole
point.

## 7. Phase 3 — Experiment: reduce GIL-contention stutter during background init

Once Phases 1–2 land, `AllyCore` construction and `initialize_run()` genuinely run on a
background thread while the Qt event loop runs concurrently on the main thread. Python's
GIL means CPU-bound pure-Python work on that background thread (and on the further
nested `ClipModelLoader` thread spawned from within it) can still cause the main thread
to visibly stutter, even though it's no longer a hard freeze.

Add, near the very top of `run.py` (before any heavy work, right after the existing
imports), a call to lower Python's GIL switch interval:

```python
import sys
sys.setswitchinterval(0.001)  # default is 0.005s; smaller = more frequent GIL handoff,
                               # trading a small amount of total throughput for a more
                               # responsive UI thread while background init threads run.
```

Include a one-line comment (as shown above) explaining why this exists, so a future
reader doesn't mistake it for dead/experimental code and remove it. This is a genuinely
standard technique for exactly this class of problem (a GUI thread + a CPU-bound worker
thread in the same CPython process) and is low-risk/easily revertible if it doesn't
help.

**This is explicitly an experiment, not a guaranteed fix.** After applying it, re-run
the app and both (a) capture the Phase 0-style timing log again, and (b) manually try
dragging/resizing the overlay window during the background-init window, to get a
subjective read on responsiveness. Report both the objective timing numbers and the
subjective responsiveness observation in the changelog entry. If it makes no measurable
or perceptible difference, leave it in anyway (it's harmless) but say so plainly in the
report rather than overstating the effect.

## 8. Verification (do this after Phases 1–3 are all applied)

1. Run the app fresh (`python run.py`, no special flags).
2. Capture the full startup log again (same method as Phase 0.3).
3. Confirm, from the new log:
   - The heavy-import timing block from Phase 0 step 5 no longer appears *before*
     `app.exec()` in the causal chain — it should now be interleaved with (or after)
     evidence that the event loop has started (e.g. the Phase 2 log line should appear
     very early, well before the `AllyCore`/import timing numbers that used to block it).
   - The "GUI event loop running..." log line's own timestamp/elapsed figure should be
     small — a rough proxy for "the window became interactive quickly."
4. Manually confirm the window can be dragged/resized during the background
   initialization window (the period between the Phase 2 log line and
   `AllyCore.initialize_run()` completing). This is the actual bug being fixed — the
   timing numbers are supporting evidence, not the goal itself.
5. Append the before/after comparison (old 3.88s-style figure vs. new figures, plus the
   drag-responsiveness observation) to the same `docs/changelog.md` entry from Phase 0 —
   one combined entry covering the whole investigation and fix, not two separate ones.

## 9. Deliverables checklist

- [ ] Phase 0 instrumentation added and a real captured timing log obtained
- [ ] `docs/changelog.md` entry with Phase 0 findings (which hypothesis confirmed/refuted)
- [ ] Phase 1 import relocation in `main.py`'s `run_qt_app_with_overlay()`
- [ ] Phase 2 `QTimer.singleShot(0, ...)`-deferred log fix in `run.py`
- [ ] Phase 3 `sys.setswitchinterval(0.001)` added to `run.py` with explanatory comment
- [ ] Verification re-run completed, before/after numbers + drag-responsiveness
      observation appended to the same changelog entry
- [ ] Confirm no thread-locking, memory/DB schema, or GUI visual changes were made
      anywhere in this pass (scope check against §"Non-goals" above)
- [ ] Full type hints preserved on any new/modified function signatures per `CLAUDE.md`

If any step surfaces something that requires a real design decision (not just "which
line does this import go on"), stop and write it up in the changelog/report rather than
deciding it yourself — flag it for the next round.

---

## Notes for Claude's code review (ZooCode: ignore this section)

- Priority check: confirm the Phase 0 findings actually validated hypothesis 1 (heavy
  imports blocking `app.exec()`). If ZooCode's diagnostic log shows something different
  — e.g. the 3.88s really is inside `ProdOverlayWindow.__init__` or
  `run_header_splash()` — the Phase 1 fix as specified may be necessary but not
  sufficient, and a follow-up spec targeting whatever `header.py`/`overlay_window.py`
  turned out to be doing will be needed. Don't assume Phase 1 alone closed the loop
  just because it was applied — check the actual before/after numbers.
- Check that the import relocation in `run_qt_app_with_overlay()` didn't silently break
  anything via closure/scoping weirdness — e.g. `AllyCore` referenced in `_async_init`'s
  body needs the import to actually be inside `_async_init`, not just "somewhere in the
  file" — verify by reading the diff, not just trusting the deliverables checklist.
- Check whether ZooCode registered `header.py` in `logger.py`'s `REGISTRY` dict sanely
  (picked an unused color, sensible display name) rather than colliding with an
  existing entry.
- The `sys.setswitchinterval(0.001)` change is a genuine trade-off (more context-switch
  overhead project-wide, in exchange for UI responsiveness specifically during startup).
  If it turns out to have no effect per ZooCode's own report, consider in review whether
  it's worth keeping at all, or whether it should be scoped more narrowly (e.g. only set
  during the startup window, then restored to default via
  `sys.setswitchinterval(0.005)` once `AllyCore.initialize_run()` completes) rather than
  left changed for the whole process lifetime. This wasn't specified as required in the
  task above (left as "leave it in anyway, it's harmless") — worth a second look given
  it's a process-global setting affecting every thread for the app's entire lifetime,
  not just the startup window.
- Confirm the changelog entry actually lives in `docs/changelog.md`, not
  `docs/ally_decision_log.md` — this is diagnostic/bugfix work per the doc-map
  distinction in `CLAUDE.md`, not new design rationale, even though the switchinterval
  bit borders on being a real project-wide decision worth a one-line mention in the
  decision log too if it sticks after review.
