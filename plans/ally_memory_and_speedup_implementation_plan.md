# Ally: Memory System Correctness Pass + Speedup Pass

## How to use this document

This covers **two separate passes**. Do not interleave them — finish and
verify Pass 1 (memory correctness) before starting Pass 2 (speedup),
since several speedup items assume Pass 1's fixes are already in place.

You (the implementing AI) should treat each numbered Step below as a
*starting point*, not a fully-specified task. Per this project's existing
convention (see `plans/` directory for examples — e.g.
`plans/mtga_entity_resolver_plan.md`, `plans/memory_pipeline_architecture_plan.md`),
write your own sub-plan `.md` under `plans/` for any Step that touches
more than 1-2 files before writing code, and subdivide further if a Step
still feels too large once you're in it. Small, verifiable increments are
strongly preferred over one large change — this codebase's existing
pattern is one focused module/file per concern, with the reasoning
written into the module docstring (see `state/sandbox.py`,
`state/entity_registry.py`, `collectors/log_reader.py` for the house
style of docstring-as-design-rationale).

**Ground rules that apply throughout both passes:**

- **No manual step for forward progress.** Anything you build must work
  automatically end-to-end. Manual/inspection tools are fine as optional
  aids, never as a required step (this is the project's core design
  principle — see `docs/ally_decision_log.md` intro).
- **Update `docs/ally_decision_log.md`** as you go, following its own
  stated convention: append a new dated section, never rewrite existing
  history. If a Step here changes something already decided in that doc,
  say so explicitly in the new entry ("supersedes X").
- **Testing convention**: follow the two-tier pattern already established
  by `plugins/mtga/` (see `plugins/mtga/README.md`) — fixture-based fast
  tests that always run (`unittest`, no external dependencies, skip
  cleanly when real data/environment isn't present) plus, where relevant,
  a real-environment guarded tier. Put new tests next to the module they
  test, following existing filenames like `collectors/test_log_reader.py`.
- **Don't touch Pass 2 files while doing Pass 1**, and vice versa, so the
  two passes stay independently reviewable.

---

# PASS 1 — Memory System Correctness

## Context (read before starting)

The memory system (`memory/`) was built by another AI from
`docs/ally_decision_log.md`'s design and appears to run without errors,
but several pieces don't actually do what the design doc says. This pass
fixes those gaps. Read `docs/ally_decision_log.md`'s "Memory system"
section in full before starting — everything below assumes that context.

The core issue: `save_id` (used to key narrative memory) is currently
generated fresh with `uuid.uuid4()` on every launch of `main.py`, so the
DB read-path that's supposed to resume a run's memory never actually
finds anything. Several other pieces (cross-session tier, trigger
system, entity persistence) were stubbed or partially wired around this
same gap. Steps 1-3 below fix the root cause; Steps 4-7 fix things that
depend on it or were separately incomplete.

---

## Step 1: `SaveTracker` — resolve and track `save_id` correctly

**Goal**: replace `uuid.uuid4()` save_id generation in `main.py` with a
real mechanism so that reopening Ally while a run is still genuinely in
progress resumes that run's memory, and closing a run out (see Step 3)
starts a clean new one.

**New file**: `memory/save_tracker.py`

**New DB table** (add to `memory/db.py`, `MemoryDB._init_db`):

```
save_sessions:
    id INTEGER PRIMARY KEY AUTOINCREMENT
    player_id TEXT NOT NULL
    game_id TEXT NOT NULL
    save_id TEXT NOT NULL
    status TEXT NOT NULL          -- "open" or "closed"
    started_at DATETIME
    last_active_at DATETIME
    UNIQUE(player_id, game_id, save_id)
```

**`SaveTracker` API** (design, not literal code — use your judgment on
exact signatures, but keep these responsibilities separate):

- `resolve_save_id(player_id, game_id, idle_window_seconds=7200) -> tuple[str, bool]`
  Called once at startup (`main.py`, replacing the `uuid.uuid4()` line).
  Looks up the most recent **open** `save_sessions` row for
  `(player_id, game_id)`. If `last_active_at` is within
  `idle_window_seconds`, reuse that `save_id` (return `(save_id, False)`
  — not new). Otherwise generate a new `save_id`, insert a new open row,
  return `(save_id, True)`. This is the "was Ally itself just closed and
  reopened mid-run" case — it is NOT trying to detect game-state run
  boundaries (that's Steps 2-3).
- `touch(player_id, game_id, save_id)` — updates `last_active_at` to now.
  Call this from `NarrativeMemoryManager.record_turn()` (every turn and
  every chat message both count as activity).
- `close(player_id, game_id, save_id)` — marks the row `status="closed"`.
  A closed `save_id` must never be returned by `resolve_save_id` again.
  This method should NOT itself do any distillation — that's
  `NarrativeMemoryManager`'s job (Step 4). `SaveTracker` only tracks
  open/closed state; keep it dumb, same pattern as `StateSandbox` being
  deliberately dumb.

**Wire into `main.py`**: replace
`save_id=f"session_{uuid.uuid4().hex[:8]}"` with a call to
`SaveTracker.resolve_save_id(...)`. `player_id` is currently hardcoded
`"default_player"` — leave that as-is, it's out of scope here.

**Tests**: `memory/test_save_tracker.py` — new game_id gets a new
save_id; a recently-active save_id is reused; a stale (past idle
window) save_id is NOT reused and a new one is created instead; a
closed save_id is never returned.

---

## Step 2: `RawObservation` gets optional run-boundary fields

**Goal**: give any Collector that has a *real* signal for "this run/match
just started/ended" a way to say so directly, bypassing guesswork
entirely, following the same optional-field pattern already used for
`bootstrap_ready` in `collectors/base.py`.

**Edit `collectors/base.py`**: add two fields to `RawObservation`,
both defaulting to `False`:
```
run_started: bool = False
run_ended: bool = False
```

No other code changes needed in this Step — no current Collector sets
these yet. This is purely adding the seam. The concrete consumer
(MTGA's `MatchGameRoomStateType_Playing` / `MatchCompleted` signal,
already documented in `docs/mtga_integration_notes.md` §3.4) will set
`run_started`/`run_ended` when `plugins/mtga/collector.py` is eventually
built (MTGA integration Step 9, Task C — separate, already-planned work,
not part of this document). Note this explicitly in your decision-log
entry so it's clear why the field exists with no current producer.

---

## Step 3: Ally-detected run boundary (semantic fallback)

**Goal**: for games with no native "run ended" signal (i.e. every
screen-capture game today), let Ally itself flag an unambiguous
game-over/victory/run-complete screen when it sees one in the normal
course of reasoning about the current turn. This is a semantic judgment,
so it belongs to Ally, not Scribe — Scribe stays pure perception per the
existing air-gap rule (`docs/ally_decision_log.md` "Air-gap" section).
Do not add this to Scribe's schema or prompts.

**Edit `schema/schema.py`** — add to `AllyOutput`:
```python
run_boundary: Literal["none", "run_ended"] = "none"
```

**Edit `prompts/ally.py`** (`ALLY_PROMPT_TEMPLATE`) — add an instruction
along these lines (adapt wording to match the existing prompt's voice):
"If the current screen is an unambiguous end-of-run screen — victory,
defeat, game over, run complete — set run_boundary to 'run_ended'.
Only do this for a genuine terminal screen, not a story beat, cutscene,
or dialogue that merely sounds final. When in doubt, use 'none'."

**Wire the priority rule in `main.py` (`run_turn`)**: after both the
observation and the Ally response are available for a turn, determine
whether the run ended using this priority:
1. If `observation.run_ended` is `True` (a collector's native signal,
   Step 2) — use that. Ally's own `run_boundary` field is not even
   consulted this turn.
2. Otherwise, if `ally_output.run_boundary == "run_ended"` — use that.

When either fires, call into the closing logic from Step 4 (do not call
`SaveTracker.close()` directly from `main.py` — go through
`MemoryManager`/`NarrativeMemoryManager` so distillation happens
atomically with the close; see Step 4).

**Important**: write this priority-ordering logic as a small,
independently testable function (e.g.
`resolve_run_ended(observation, ally_output) -> bool`) rather than
inlining it into `run_turn`, so it can be unit tested without spinning
up the full turn loop.

**Tests**: `test` for `resolve_run_ended` covering: collector signal
true + Ally none → True; collector signal false + Ally run_ended → True;
both false/none → False; collector true always wins even if Ally also
says run_ended (should still just resolve True once, not double-fire).

---

## Step 4: A genuine cross-session memory tier

**Goal**: currently `flush_to_cross_session()` just calls
`flush_to_long_term()` again — there is no actual `(player_id, game_id)`-
scoped memory independent of `save_id`. This step builds that real
fourth tier per the original decision log design.

**New DB table** (`memory/db.py`):
```
cross_session_memory:
    id INTEGER PRIMARY KEY AUTOINCREMENT
    player_id TEXT NOT NULL
    game_id TEXT NOT NULL
    summary TEXT NOT NULL
    save_id_closed TEXT NOT NULL   -- which run produced this entry
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
```
Append-only, like `personality_journal` — never overwritten, only added
to. `NarrativeMemoryManager.build_context()` reads the single most
recent row for `(player_id, game_id)` and surfaces it first (it's the
most durable memory available, should lead the context, above the
long-term summary of the *current* run).

**New prompt** (`prompts/narrative.py`): add
`CROSS_SESSION_SUMMARY_PROMPT` — distinct from the existing
`NARRATIVE_LONG_TERM_PROMPT`. This one takes the just-closed run's
long-term summary AND the previous cross-session summary (if any, else
note "this is the first recorded run") and asks the model to synthesize
an updated cross-session summary — i.e. this is a merge/update step, not
a copy. Keep the instruction explicit that this should stay high-level
("what we generally know about this game and how these runs tend to go"),
not a blow-by-blow of the just-finished run.

**New method on `NarrativeMemoryManager`**: `close_run()` (name it
whatever fits, but it should be the single entry point Step 3 calls
into). Responsibilities, in order:
1. If there's no long-term summary yet for the current run, call the
   existing `flush_to_long_term()` first so there's something to
   synthesize from.
2. Load the previous cross-session summary for `(player_id, game_id)`
   from `cross_session_memory` (if any).
3. Call the model with `CROSS_SESSION_SUMMARY_PROMPT`, save the result
   as a new row in `cross_session_memory`.
4. Call `SaveTracker.close(player_id, game_id, save_id)` (inject
   `SaveTracker` into `NarrativeMemoryManager`, or into `MemorySystem`
   and delegate — your call on wiring, just keep `SaveTracker` itself
   dumb per Step 1).

**Keep the existing `flush_to_cross_session()` behavior as a safety net
only**: it's currently called from `main.py`'s `finally` block on
Ctrl+C/exit. Keep that call, but it should now just mean "close out
whatever's still open" (i.e., call the new `close_run()` if the current
save_id is still open) — not the primary trigger. The primary trigger
is the mid-session `run_boundary` signal from Step 3.

**Tests**: `memory/test_narrative.py` (new or extend if one exists) —
closing a run writes exactly one new `cross_session_memory` row;
`build_context()` includes the cross-session summary when present;
a second run for the same game_id merges with (not just overwrites) the
first cross-session entry — assert the prompt actually received the
prior summary as input (mock the provider call and check its `contents`).

---

## Step 5: Wire the trigger system for real, decouple buffer size from flush cadence

**Goal**: `memory/triggers.py` defines `TurnCountTrigger`,
`SalienceEventTrigger`, and `ExplicitAllyTrigger`, but only
`TurnCountTrigger` is ever actually used, and it's currently tied 1:1 to
`short_term_capacity` (the buffer size), which means you can't tune one
without the other.

**Add a `CompositeTrigger`** to `memory/triggers.py`:
```python
class CompositeTrigger(Trigger):
    def __init__(self, triggers: list[Trigger]):
        self.triggers = triggers
    def should_trigger(self, context: dict) -> bool:
        return any(t.should_trigger(context) for t in self.triggers)
```

**Edit `NarrativeMemoryManager.__init__`**: default `flush_trigger` to a
`CompositeTrigger([TurnCountTrigger(interval=medium_flush_interval),
SalienceEventTrigger(importance_threshold=8),
ExplicitAllyTrigger()])` instead of a bare `TurnCountTrigger`. Add a new
constructor parameter `medium_flush_interval: int = 8` (separate from
`short_term_capacity`, even though they may share a default value —
they are conceptually different knobs, see Step 6 for why this matters).
Thread this new parameter up through `MemorySystem.__init__`
(`memory/manager.py`) the same way `short_term_capacity` already is.

**Note**: `record_turn(importance=..., explicit_checkpoint=...)`
already builds the right `context` dict — this Step is purely about
making sure something downstream actually reads `importance` and
`explicit_checkpoint`, which today nothing does.

**Tests**: exercise each trigger type independently through
`CompositeTrigger`, then confirm `NarrativeMemoryManager.record_turn`
fires a medium-term flush on a high-importance call even when the turn
count wouldn't have triggered one on its own.

---

## Step 6: Fix chat messages corrupting turn-based flush cadence

**Goal**: `main.py`'s chat handler currently calls
`mm.record_turn(sandbox.turn, ...)`, reusing whatever `sandbox.turn`
currently is. Since `sandbox.turn` only advances on real game turns,
several chat messages sent back-to-back can all land on the same turn
number, and — worse — chat activity can accidentally land exactly on a
turn-count multiple and trigger a flush that has nothing new to
summarize.

**Fix**: give `NarrativeMemoryManager` its own internal monotonic
counter, independent of the caller's `sandbox.turn`. Add
`self._entry_count` (or similar), incremented once per `record_turn()`
call regardless of whether the caller is a real game turn or a chat
message. Use `self._entry_count` (not the passed-in `turn` argument) as
the value `TurnCountTrigger` checks against. **Keep the passed-in
`turn` argument as-is for display/logging purposes** (it's still useful
to know which game-turn a memory entry corresponds to) — just stop
using it as the trigger-cadence counter.

This is a small, surgical change — don't restructure `record_turn`'s
signature, just change what value feeds the trigger check internally.

**Tests**: three `record_turn` calls in a row with the *same* `turn`
argument (simulating three chat messages between game turns) should
still count as three distinct entries toward the flush interval, not
zero.

---

## Step 7: `EntityRegistry` persistence (per your decision: wire it up)

**Goal**: `state/memory.db`'s `entities` table exists but
`EntityRegistry` is still purely in-memory, reset every process launch.
Wire it to actually load/save.

**Scope decision already made**: persistence is scoped to
`(player_id, game_id, save_id)` — i.e., an entity registry survives an
Ally restart *while the same run is still open* (consistent with what
`save_id` means after Step 1), matching the run-scoped design already
described in `docs/ally_decision_log.md`'s Entity Registry section. This
is NOT the same as true cross-session entity carryover across different
runs — the decision log already flags that as a future candidate; don't
build it now, just note it stays flagged as future work in your
decision-log entry.

**Schema change needed**: the existing `entities` table
(`memory/db.py`) has no `save_id` column. Add one via an idempotent
migration — SQLite's `CREATE TABLE IF NOT EXISTS` won't add a column to
an already-existing table, so guard the `ALTER TABLE` with a
try/except (SQLite raises if the column already exists) or check
`PRAGMA table_info` first. Follow whichever pattern is simpler to read;
add a comment explaining why the guard exists, since a naive reader
might think it's dead code.

**`EntityRegistry` changes** (`state/entity_registry.py`):
- Constructor needs `player_id`, `game_id`, `save_id`, and a `MemoryDB`
  reference (or an injected repository object — your call, but don't
  give `EntityRegistry` raw SQL, keep that in `memory/db.py` per the
  existing separation of concerns).
- On construction, load existing entities for this
  `(player_id, game_id, save_id)` scope from the DB into `self._entities`
  and rebuild `self._external_id_index` from the loaded data (the
  in-memory `Entity` dataclass and the DB row need a clean two-way
  mapping — write explicit `to_row()`/`from_row()` helpers rather than
  scattering field-by-field conversion across methods).
- After `resolve_or_create()` finishes updating `self._entities`,
  upsert the touched entities to the DB (insert new ones, update
  `facts`/`aliases`/`last_seen_turn`/`entity_type` for existing ones on
  a match against `entity_id`).
- `aliases` and `facts` are lists — the existing `entities` table already
  stores them as `TEXT`, so keep using the same serialization approach
  already implied there (JSON-encode on write, decode on read).

**Wire construction site**: `main.py` currently does
`registry = EntityRegistry()` once, outside the loop. Update this to
pass `player_id`, `game_id` (from the resolved collector config or
`"adhoc_image"` for the single-file path), `save_id` (from Step 1's
`SaveTracker.resolve_save_id`), and a `MemoryDB` instance.

**Tests**: `state/test_entity_registry_persistence.py` — create
entities, construct a fresh `EntityRegistry` with the same
`(player_id, game_id, save_id)`, confirm it loads them back including
`external_id` resolution still working post-reload; confirm a
*different* `save_id` starts with an empty registry.

---

## Step 8: Update the decision log

Add one new dated section to `docs/ally_decision_log.md` covering
everything in this pass: `save_id` semantics (run-scoped, resolved via
idle-window heuristic with a collector-native override seam), the real
cross-session tier and how it differs from long-term, the composite
trigger, the turn-counter fix, and entity persistence scope (explicitly
note true cross-session entity carryover is still deferred, not built).
Follow the doc's own stated convention — don't rewrite the existing
"Memory system" section, append new content that supersedes the
specific claims that changed (the `flush_to_cross_session` description,
the Entity Registry persistence status, etc.) and say so explicitly.

---

# PASS 2 — Speedup Plan (separate pass, do not start until Pass 1 is verified)

Source: `ally_speedup_plan.md` (already provided). Implement all 7
items, but note the constraints below for each — these came out of
review and should be treated as amendments to that plan, not
suggestions to skip.

## 2.1: Reduce thinking level
Straightforward. Make `Ally.decide()`'s `thinking_level` a constructor
parameter with a sane default, don't hardcode `"HIGH"` in the method
body. Low risk, do this first.

## 2.2: Context & memory token limits
Now simpler after Pass 1 Step 5/6 decoupled `short_term_capacity` from
flush cadence — tune buffer size and flush interval independently.

## 2.3: Element filtering in State Sandbox
**Caution**: Scribe's UI-mode prompt (`prompts/scribe.py`) deliberately
extracts every interactable element, including ones Ally may reference
by `target_entity_ids` in its actions. Filtering must not drop anything
an action could point to. Prefer filtering only elements Scribe itself
could plausibly flag as decorative (this may require a small Scribe
schema addition — e.g. an `is_decorative` bool on `ScreenElement` — decide
this in your own sub-plan) over a generic heuristic applied after the
fact with no signal from Scribe about what's safe to drop.

## 2.4: Semantic diff guard
This is the concrete mechanism already flagged as deferred in
`docs/ally_decision_log.md` ("Turn-gating" section, last paragraph) —
implement that specific idea, don't invent a new one. Concretely:
`GenericHudCollector` (`collectors/configured_collector.py`) needs to
retain last turn's `ConfirmedFacts` (it currently discards them each
`capture()` call). Compare this turn's `ConfirmedFacts` against last
turn's; if identical, skip invoking Scribe/Ally for this turn even if
SSIM detected pixel-level motion. **This only helps calibrated-OCR
games** (where `ConfirmedFacts` exist) — note in your sub-plan that it's
a no-op for uncalibrated screens and for MTGA's `structured_state` path
(that path would need its own diff check on the accumulated game state,
which is a separate, not-yet-scoped piece of work — don't build it here).

## 2.5: Streamline prompts and schemas
**Caution**: several specific clauses in `ALLY_PROMPT_TEMPLATE`
(no brackets outside the actions list, natural naming instead of raw UI
labels, "have an opinion, don't just list options neutrally") were added
to fix real observed bugs during the FTL integration pass — see
`docs/ally_decision_log.md`'s FTL section referenced from memory (also
cross-reference the "Five FTL-specific bugs fixed" note in project
memory if available to you). Do not do a wholesale rewrite. Trim only
genuinely redundant wording, and after any change, manually re-check
output against each of those specific behaviors (no brackets in
analysis text, proper names not "Crew Member X", etc.) before
considering this done.

## 2.6: Asynchronous pipeline execution
**Highest risk item — do this last, and treat locking as a blocking
prerequisite, not a nice-to-have.** There is already an unguarded
concurrent writer today: the GUI chat handler
(`main.py`'s `on_send_message`) runs `ally.chat()` on a background
`threading.Thread` that reads/writes `sandbox`, `registry`, and
`memory_manager` — the same objects the main loop's `run_turn()`
mutates, with no locking at all. Making the main capture loop itself
threaded on top of this doubles the race surface on `StateSandbox` and
`EntityRegistry`, neither of which is currently thread-safe.

Before touching the main loop:
1. Add a single lock (a plain `threading.Lock` is fine) guarding every
   read-modify-write sequence against `sandbox`, `registry`, and
   `memory_manager` from *any* thread, including the existing chat
   thread. Write this as its own small sub-plan and get it working and
   tested in isolation first.
2. Only then move Scribe/Ally inference calls into a
   `ThreadPoolExecutor` per the original proposal, using the same lock
   for any shared-state access on completion.

If, once you're in this Step, a lock-per-object model turns out to be
error-prone to reason about correctly, prefer a single-writer queue
(all mutations to shared state happen on one dedicated thread, other
threads submit work to it) over multiple fine-grained locks — it's
easier to verify correct and matches this project's general preference
for simple, obviously-correct mechanisms over clever ones.

## 2.7: GUI settings integration
Before adding new controls, fix the existing gap: `gui/settings_window.py`
already writes a full settings dict to `configs/user_config.json` via
`save_user_config()`, but only `enable_downscaling` /
`downscale_max_size` are actually read anywhere
(`collectors/screen_collector.py`). Every other key in that settings
window — model selections, `default_personality`, all the
`ChangeDetector`/`ScreenClassifier`/`ScreenBootstrapper` thresholds —
is currently write-only. Before adding a thinking-level dropdown (which
this pass needs, for 2.1), do a pass that makes `Scribe`, `Ally`,
`NarrativeMemoryManager`, `PersonalityMemoryManager`,
`ChangeDetector`, `ScreenClassifier`, and `ScreenBootstrapper`
construction sites all read their tunable values from
`load_user_config()` (with the current hardcoded values as fallback
defaults) instead of hardcoding them. Then add the thinking-level
control on top of a settings panel that actually does something.

---

# APPENDIX — Review notes (for the project owner / future reference; not implementation instructions)

*Implementing AI: everything below this line is background context for
a later human/AI review pass and is not part of your task list. Skip
this section.*

This plan resulted from a design discussion covering several forks that
aren't obvious from the code alone. If reviewing the implementation
later without that conversation's context, check specifically for:

- **`save_id` is run-scoped, not session-scoped.** The idle-window
  heuristic in Step 1 only governs "was Ally itself restarted mid-run" —
  it must NOT be the mechanism that decides when a run has ended. Run
  endings are decided exclusively by Step 2/3 (collector-native signal,
  with Ally's semantic `run_boundary` field as fallback, collector
  signal always taking priority when both could apply on the same turn).
  If the implementation conflates these two mechanisms — e.g. treats a
  long idle gap as itself closing out the run — that's a deviation from
  intent worth flagging.
- **The game-over-then-reload edge case was deliberately resolved by NOT
  trying to detect "same save file."** Once `run_ended` fires, the
  `save_id` closes and distills, permanently, no matter what happens
  next. A subsequent reload/new-game always gets a fresh `save_id`. Check
  that no later change tried to re-introduce same-save detection — it
  was explicitly rejected as undecidable from this pipeline's vantage
  point.
- **Cross-session memory (Step 4) must be a real, separately-keyed
  table with its own synthesis prompt** — not `flush_to_long_term()`
  called twice under a different name. Check `cross_session_memory` rows
  actually exist and that `build_context()` surfaces the most recent one
  distinctly from the current run's long-term summary.
- **Entity persistence scope (Step 7) is deliberately run-scoped
  (`player_id, game_id, save_id`), not cross-session.** True
  cross-run entity carryover was explicitly deferred, not built. If a
  later change quietly expanded the scope (or if it was never narrowed
  from a naive "just key by player_id+game_id" implementation), that's
  worth flagging — it wasn't the agreed design.
- **Pass 2 item 2.6 (async pipeline) was flagged as highest-risk and
  meant to be done last, with locking as a hard prerequisite.** Worth
  specifically checking whether locking was actually added before
  threading, or whether the implementing AI (being a smaller model)
  skipped straight to the `ThreadPoolExecutor` change and left the
  existing unguarded chat-thread race in place or made it worse.
- **Pass 2 item 2.5 (prompt trimming)**: check the FTL-specific
  behaviors (no brackets outside actions list, proper names not "Crew
  Member X", opinionated rather than neutral option-listing) are all
  still intact in whatever the trimmed prompt ends up saying.
