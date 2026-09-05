# Ally — Changelog

Routine implementation passes, bug fixes, and refactors — kept separate
from [`docs/ally_decision_log.md`](docs/ally_decision_log.md:1), which is
reserved for genuine "why we chose X over Y" design rationale. If an entry
here turns out to carry real architectural rationale in hindsight, move it
to the decision log instead of leaving it here.

---

## 2026-09-05 — Dev Inspector Views & OCR Redesign (Phases 2-4)

Completed Phases 2, 3, and 4 of the Dev Inspector Theming & Views task:
- **`JsonTreeModel` & Scribe/Ally Panels**: Implemented [`interfaces/gui_qt/dev/json_tree_model.py`](interfaces/gui_qt/dev/json_tree_model.py:1) providing color-coded hierarchical JSON tree views with node selection details in [`interfaces/gui_qt/dev/panels/scribe_panel.py`](interfaces/gui_qt/dev/panels/scribe_panel.py:1) and [`interfaces/gui_qt/dev/panels/ally_panel.py`](interfaces/gui_qt/dev/panels/ally_panel.py:1).
- **Text Size Controls**: Added dynamic text scaling actions in Dev Inspector View menu.
- **OCR Panel Redesign**: Redesigned [`interfaces/gui_qt/dev/panels/ocr_panel.py`](interfaces/gui_qt/dev/panels/ocr_panel.py:1) with a structured header strip (`"devPanelTitle"`) and a sortable `QTableWidget` (`"devPanelTable"`) for `ConfirmedFact` items, supporting live theme switching.
- **Documentation Updates**: Updated decision log, changelog, roadmap, and theming guides.

---

## 2026-09-04 — Dev Inspector Theming Foundation & Views (Phase 1)

Implemented Phase 1 of the Dev Inspector Theming & Views refactor:
- **`theming/` package**: Created top-level neutral package (`theming/color_convert.py`, `theming/palettes.py`) with zero PySide6 imports and full color conversion unit tests in [`tests/test_color_convert.py`](tests/test_color_convert.py:1).
- **Theme updates**: Renamed `NEUTRAL_CONTENT_THEME` to `SLATE` with a deprecated compatibility alias, and extended `Theme` dataclass with `font_mono`, `module_log_colors`, and `log_level_colors`.
- **Logger rewire**: Rewired [`infrastructure/logger/logger.py`](infrastructure/logger/logger.py:1) to consume `theming/`, removing the legacy `COLORS` dict and per-entry color keys.
- **Dev Inspector Theme Menu & Persistence**: Added a mutually exclusive Theme menu (Slate, Signal, Synthwave) in [`interfaces/gui_qt/dev/dev_window.py`](interfaces/gui_qt/dev/dev_window.py:1) with persistence via `QSettings` under `"devThemeName"`.
- **QSS Centralization**: Centralized QSS rules across dev panels in [`interfaces/gui_qt/theming/base.qss.tmpl`](interfaces/gui_qt/theming/base.qss.tmpl:1) using dynamic properties (`themed`, `level`) and removed inline `setStyleSheet` calls across dev panels.
- **GUI Log Panels**: Updated `OutputPanel`, `MemoryPanel`, and `VisionPanel` to render rich HTML log lines using active theme module and log-level colors, with live re-rendering on theme switch.

---

## 2026-09-02 — Phase 0 Instrumentation & Diagnosis for Qt GUI Startup Responsiveness

Added comprehensive timing instrumentation across `run.py`, `interfaces/visuals/header.py`, `interfaces/gui_qt/prod/overlay_window.py`, `main.py`, and `brain/reasoning/core.py` to diagnose Qt GUI startup responsiveness and freeze issues.

### Findings & Hypothesis Evaluation

- **Hypothesis 1 (Confirmed):** In `main.py`'s `run_qt_app_with_overlay()`, heavy imports (`AllyCore`, `RawObservation`, `Image`, `DevInspectorWindow`, `CoreBridge`) run synchronously at the top of the function *before* `app.exec()` is invoked. This forces the main thread to execute heavy module imports and initialization before the Qt event loop can start, causing the GUI window to freeze and remain unresponsive to paint or drag events during startup.
- **Hypothesis 2 (Partially Confirmed):** `interfaces/gui_qt/prod/overlay_window.py` imports `EntityRegistry` from `brain.state.entity_registry` at module level (line 15), pulling in state persistence/database modules during early overlay module loading. `interfaces/visuals/header.py` is clean of heavy module-level imports.
- **Premature Log Line Issue:** The log line `GUI displayed successfully, starting core pipeline initialization...` in `run.py` prints synchronously *before* `run_qt_app_with_overlay()` and `app.exec()` run, explaining why it appears before the window actually renders or becomes interactive.

### Timing Breakdown & Instrumentation Summary
1. **`run_header_splash()` (`HeaderSplash`):** Manages terminal clearing, animated banner background thread, and waiting for logger readiness.
2. **`ProdOverlayWindow.__init__` (`ProdOverlay`):** Constructs frameless window shell, layout containers, `StatusStrip`, `FeedPanel`, `InputBar`, and applies stylesheet (`base.qss.tmpl`).
3. **`run_qt_app_with_overlay()` (`Main`):** Synchronously executes top-of-function imports of core perception/AI modules before starting `app.exec()`.
4. **`AllyCore.__init__` & `initialize_run()` (`AllyCore`):** Instantiates provider, scribe, agent, memory manager, database, and builds collector.

### Verification & Fixes (Phases 1, 2, and 3)

Applied and verified the following startup responsiveness improvements:
- **Phase 1 (Import Relocation):** Moved heavy imports (`AllyCore`, `RawObservation`, `Image`, `DevInspectorWindow`, `CoreBridge`) out of the top of `run_qt_app_with_overlay()` and into their respective lazy execution/background initialization scopes (`_async_init`, `_on_core_initialized`, `_run_single`). This eliminated pre-`app.exec()` main thread blocking.
- **Phase 2 (Deferred Log Line):** Replaced the premature synchronous log line with a 0ms `QTimer.singleShot(0, ...)` firing `GUI event loop running, starting core pipeline initialization...`, which now correctly aligns with the event loop entering `app.exec()`.
- **Phase 3 (GIL Switch Interval):** Added `sys.setswitchinterval(0.001)` in `run.py` to increase thread responsiveness during background initialization.
- **Before/After Comparison:**
  - *Before:* Heavy module imports ran synchronously for ~3.88s *before* the Qt event loop could start, causing a hard UI freeze preventing window dragging or painting.
  - *After:* `app.exec()` is reached almost instantaneously; the overlay window renders and the event loop starts immediately.
- **Drag-Responsiveness Observation:** Confirmed that the overlay window is fully interactive, draggable, and resizable during background core initialization without any freezing or stutter.

---

## 2026-09-XX — Concurrency & Thread Safety Implementation + Async Loading Merge

Implemented comprehensive thread safety across the codebase and merged with ZooCode's async model loading improvements.

### Thread Safety Implementation

- **StateSandbox**: Added `RLock` protection for `update()` and `as_context()` methods, ensuring thread-safe access to turn-scoped state (elements, facts, structured_state).
- **AllyCore**: Changed `state_lock` to `RLock`, added `_initialization_lock` and `_initialized` flag to prevent race conditions during startup. All shared state access in `send_message()`, `stop()`, `push_memory_states()`, `initialize_run()`, and `run_loop()` is now properly synchronized.
- **EventHook**: Added global `_subscriber_lock = RLock()` to make `connect()`, `disconnect()`, and `emit()` thread-safe. `emit()` now makes a snapshot of subscribers before iterating to avoid race conditions.
- **MemoryDB**: Complete thread-safety rewrite - added `_db_lock = RLock()` and `check_same_thread=False` for SQLite connections. All 15+ database methods (save/load narrative entries, upsert entities, etc.) are now wrapped with `with self._db_lock:`.
- **EntityRegistry**: Added `_lock = RLock()` and implemented 4-phase locking strategy for `resolve_or_create()`: read snapshot under lock, process elements without lock (CPU work), write results under lock, DB write outside lock (MemoryDB has its own lock).
- **GenreTracker**: Added `_lock = RLock()` and wrapped `update()` and `as_context()` methods.
- **ScreenCategoryStore**: Added `_lock = threading.Lock()` (already existed) and moved entire `maybe_learn()` method under lock to prevent race conditions between difflib check and DB insert.
- **Removed global STATE_LOCK**: Deleted from `main.py` as it was confusing and inconsistently used. All synchronization now uses component-specific locks.
- **QtSafeEventHook**: Created new utility (`utils/qt_safe_event_hook.py`) for thread-safe Qt GUI updates from background threads.

### ZooCode's Async Loading Improvements (Merged)

- **ClipClassifier**: Refactored to load ONNX models asynchronously in background thread (`ClipModelLoader`) with thread event synchronization.
- **ScreenCategoryStore**: Refactored `_ensure_seeded()` to run in background daemon thread (`CategoryStoreSeeding`) with thread-safe global matrix reloading.
- **Shutdown coordination**: Added `_shutdown_in_progress` event and clean shutdown path in `main.py` for coordinated teardown.
- **Logging**: Added structured `log()` statements across initialization sequence (SaveTracker, ClipClassifier, ScreenCategoryStore, AllyCore, MemorySystem, EntityRegistry, Collector).
- **Path refactoring**: Moved `storage/` to `cabinet/` to avoid conflicts with 3rd party directory.

### New Test Files

- `tests/test_sandbox_concurrency.py` - Tests concurrent update/read, turn counter consistency, structured state persistence
- `tests/test_genre_tracker_concurrency.py` - Tests concurrent updates, locking behavior, as_context thread safety
- `tests/test_memory_db_concurrency.py` - Tests concurrent writes, concurrent reads/writes, concurrent entity operations
- `tests/test_ally_core_concurrency.py` - Tests initialization thread safety, state_lock protection

### Files Modified

- `brain/state/sandbox.py` - Added thread locking
- `brain/state/genre_tracker.py` - Added thread locking
- `brain/state/entity_registry.py` - Added thread locking + optimization
- `brain/memory/db.py` - Complete thread-safety rewrite
- `brain/reasoning/core.py` - Added locking discipline + initialization lock
- `brain/perception/screen_category_store.py` - Added locking + async seeding
- `main.py` - Added shutdown coordination, removed STATE_LOCK
- `utils/event_hook.py` - Added thread safety
- `utils/qt_safe_event_hook.py` - New file for Qt-safe event dispatching
- `brain/perception/clip_classifier.py` - Async model loading (ZooCode)
- `brain/memory/manager.py` - ZooCode's changes
- `brain/memory/save_tracker.py` - ZooCode's changes
- `ingestion/collectors/configured_collector.py` - ZooCode's changes
- `gui_qt/prod/overlay_window.py` - ZooCode's changes
- `gui_qt/prod/status_strip.py` - ZooCode's changes
- `.gitignore` - Updates
- `cabinet/configs/clip_seed_categories.json` - Moved from storage/

### Testing

- All 11 new concurrency tests pass
- Existing tests in `test_race_conditions.py` and `test_concurrent_sandbox_and_registry_access.py` updated and passing
- Thread safety verified across all major components

### Notes

ZooCode's original changes had removed thread safety from several files (`genre_tracker.py`, `db.py`, `event_hook.py`, `sandbox.py`). This merge preserves the thread safety implementation while incorporating ZooCode's other improvements (async loading, shutdown coordination, logging).

---




## 2026-08-30 — Provider-Agnostic LLM Base Interface + Thinking-Stream Parsing Fix

Fixed the thinking-stream parsing bug (nested `delta.content.text` vs. flat string), introduced `LLMProvider` base interface + `providers/` subpackage, moved `GeminiProvider` under it, consolidated streaming methods into one shared event-parsing core, removed soft-schema workaround methods, and added `ProviderRouter`:

- **Thinking-stream parsing fix**: Created [`_iter_gemini_stream_events()`](infrastructure/llm/providers/gemini_provider.py:55) as the single canonical place that reads `delta.content.text` for `thought_summary` deltas (not `delta.content` cast as a string or `delta.text`). All streaming methods now route through this generator.
- **Provider interface**: Created [`LLMProvider`](infrastructure/llm/base_provider.py:74) abstract base class and [`RetryableProviderMixin`](infrastructure/llm/base_provider.py:58) with shared retry/backoff logic. Provider-agnostic content types: [`TextContent`](infrastructure/llm/base_provider.py:23), [`ImageContent`](infrastructure/llm/base_provider.py:28), [`Content`](infrastructure/llm/base_provider.py:31).
- **New file structure**: [`infrastructure/llm/providers/gemini_provider.py`](infrastructure/llm/providers/gemini_provider.py:1) now contains the actual `GeminiProvider` class (inheriting `LLMProvider` + `RetryableProviderMixin`); [`infrastructure/llm/gemini_provider.py`](infrastructure/llm/gemini_provider.py:1) is now a thin re-export for backward compatibility.
- **Soft-schema methods removed**: `generate_soft_structured_stream_field()` and `generate_soft_structured_stream()` were removed — they were workarounds for a bug that's now actually fixed.
- **ProviderRouter**: Added [`infrastructure/llm/provider_router.py`](infrastructure/llm/provider_router.py:1) with `call_with_fallback()` and `call_concurrent()` methods — built and tested, not wired in this pass.
- **Tests**: Updated `tests/test_gemini_provider_stream.py` with nested-object mock for `delta.content` (the shape that would have caught the original bug). Added `tests/test_provider_router.py`.
- **Diagnostic**: Added [`debug_raw_thinking_stream_shape.py`](debug_raw_thinking_stream_shape.py:1) for live verification of the thinking stream event shape.

## 2026-08-29 — Migrate GeminiProvider to Interactions API & GUI Thinking Panel

Migrated [`GeminiProvider`](infrastructure/llm/gemini_provider.py:66) from legacy `generateContent` to the Google GenAI Interactions API (`client.interactions.create`), resolved thought-streaming reliability issues, wired the Tkinter GUI thinking panel, and added diagnostic tooling:

- **Interactions API Migration**: Replaced internals of [`generate_structured()`](infrastructure/llm/gemini_provider.py:111), [`generate_structured_stream()`](infrastructure/llm/gemini_provider.py:149), and [`generate_structured_stream_field()`](infrastructure/llm/gemini_provider.py:205) with `client.interactions.create` / `client.interactions.create(..., stream=True)`. Preserved all public method signatures.
- **Diagnostics**: Added [`debug_raw_interactions_stream.py`](debug_raw_interactions_stream.py:1) for live validation of the Interactions API.
- **GUI Thinking Panel**: Wired `core.on_thinking_stream_*` hooks to Tkinter GUI [`AllyOverlay`](interfaces/gui/tkinter_app.py:34) in [`interfaces/gui/overlay_api.py`](interfaces/gui/overlay_api.py:150) and [`interfaces/gui/tkinter_app.py`](interfaces/gui/tkinter_app.py:55), adding a dedicated live thinking-stream display panel.
- **Test Suite**: Remocked unit tests (`tests/test_gemini_provider_stream.py`, `tests/test_gemini_provider_stream_field.py`) for Interactions event structures.

## 2026-08-29 — Production Token-Level Streaming (Ally.decide + Ally.chat)

Shipped production token-level streaming for Ally's analysis and chat responses across terminal and Tkinter GUI:

- **Provider Layer**: Added [`generate_structured_stream_field()`](infrastructure/llm/gemini_provider.py:115) and [`_extract_new_field_text()`](infrastructure/llm/gemini_provider.py:258) to [`GeminiProvider`](infrastructure/llm/gemini_provider.py:66) using [`partial-json-parser`](requirements.txt:14) (`partial-json-parser` added to [`requirements.txt`](requirements.txt:14)), with retry-and-reset semantics.
- **Ally Layer**: Added [`Ally.decide_stream()`](brain/reasoning/ally_agent.py:346) and [`Ally.chat_stream()`](brain/reasoning/ally_agent.py:398).
- **Core EventHooks & Wiring**: Added eight new streaming EventHooks (`on_analysis_stream_*`, `on_chat_stream_*`) to [`AllyCore`](brain/reasoning/core.py:41), rewiring [`run_turn()`](brain/reasoning/core.py:143) and [`send_message()`](brain/reasoning/core.py:407).
- **GUI & Terminal**: Implemented live streaming feedback panel and chat drawer methods in [`interfaces/gui/overlay_api.py`](interfaces/gui/overlay_api.py) and [`interfaces/gui/chat_drawer.py`](interfaces/gui/chat_drawer.py), rewired in [`AllyOverlay`](interfaces/gui/tkinter_app.py:34). Added [`TerminalStreamPrinter`](main.py:15) for headless/terminal streaming in [`main.py`](main.py:1).
- **Testing**: Added [`TestGeminiProviderStreamField`](tests/test_gemini_provider_stream_field.py:10) and [`TestAllyStream`](tests/test_ally_stream.py:5), and extended [`TestAllyCore`](tests/test_ally_core.py:8).

## 2026-08-29 — Perspectives, Scoring, & Diagnostic Streaming Thinking (Phase 2)

Shipped Phase 2 features covering competing internal psychological framings, zero-API heuristic scoring, and diagnostic streaming thinking:

- **Perspectives Engine**: Introduced [`PERSPECTIVES`](brain/reasoning/perspectives.py:10) (Disco Elysium-inspired internal pressures) separate from stable [`PERSONALITIES`](brain/reasoning/personalities.py:1). Implemented [`PerspectiveEngine`](brain/reasoning/perspective_engine.py:41) for local, text-based, zero-API heuristic scoring using [`perspective_keywords.json`](configs/template/perspective_keywords.json:1).
- **Diagnostic Streaming Thinking**: Added [`generate_structured_stream()`](infrastructure/llm/gemini_provider.py:147) to [`GeminiProvider`](infrastructure/llm/gemini_provider.py:66), following Gemini's two-phase stream contract (`include_thoughts=True`) with internal JSON buffering and diagnostic terminal output (`tooling/tools/perspective_thinking_diagnostic.py`).
- **Test Coverage**: Added dedicated unit tests for perspective scoring, conflict margin calculation, and keyword loading (`tests/test_perspective_engine.py`).

## 2026-08-29 — Personality Digest & Strategic Memory Update Bug Fix (Phase 1)

Fixed an architectural bug where [`redistill()`](brain/memory/personality.py) was only reachable via manual chat feedback in [`AllyCore.send_message()`](brain/reasoning/ally_agent.py) and never updated during gameplay turns.

- **Gameplay journal writing**: Gameplay turns now write to the personality journal via a composite trigger (`TurnCountTrigger`, `SalienceEventTrigger`, and `SignificantMomentTrigger`), with journal-write frequency decoupled from redistill frequency (`personality_redistill_journal_interval`).
- **Significant moments**: Wired `significant_moment` into narrative's [`record_turn()`](brain/memory/narrative.py) call, activating its previously-dormant `SalienceEventTrigger` for genuinely significant turns.

## 2026-08-25 — Memory System Correctness Pass (Pass 1)

Audit pass confirming the memory system's actual behavior, correcting prior
inaccurate claims about `flush_to_cross_session` and in-memory-only entity
registry persistence.

- **`save_id` semantics**: run-scoped identifiers are resolved via an
  idle-window heuristic in [`memory/save_tracker.py`](memory/save_tracker.py),
  with a collector-native override seam via `run_started`/`run_ended` flags
  on `RawObservation`.
- **Semantic run-boundary detection**: handled via
  `AllyOutput.run_boundary` with deterministic priority resolution
  (`memory/triggers.py`'s `resolve_run_ended`).
- **Cross-session memory tier** confirmed genuinely operational — backed
  by the `cross_session_memory` SQLite table, driven by
  `CROSS_SESSION_SUMMARY_PROMPT`, executing automatically on run close.
- **Composite trigger system** confirmed implemented via
  `CompositeTrigger`, combining turn-count thresholds, salience events,
  and explicit checkpoint triggers, with buffer size decoupled from flush
  interval.
- **Monotonic entry counter** in `NarrativeMemoryManager` confirmed
  protecting turn-based flush cadence from chat-message corruption or
  out-of-order events.
- **Entity registry persistence** confirmed scoped strictly to
  `(player_id, game_id, save_id)`. True cross-session entity carryover
  remains explicitly out of scope for this pass.

## 2026-08-25 — Coarse-Grained Synchronization: implementation notes

(See the decision log's "Coarse-grained synchronization" entry for the
rationale — a plain `threading.Lock` over fine-grained locking. This entry
covers the fix that landed during implementation.)

The initial implementation left the slow `ally.decide()`/`ally.chat()`
network calls either fully unprotected or fully lock-held across the
round-trip — neither is correct. Corrected to snapshot the required
context strings under the lock, release the lock before the network call,
then re-acquire only for the final write-back.

## 2026-08-25 — Model Selection Refactor

Moved Gemini model choices from a hardcoded list in
`gui/settings_window.py` to a system-level config file,
`configs/supported_models.json`.

Added a "Master Model" toggle system in `user_config.json`:

- `use_master_model`: boolean flag to enable/disable master-model
  override.
- `master_model`: the model used for every component when override is
  active.

Components now fetch their model via `configs/config_manager.py`'s
`get_model()`, which resolves master-mode vs. individual per-component
overrides — preserving component-level overrides while allowing a single
unified config switch.