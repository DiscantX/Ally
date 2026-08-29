# Ally — Changelog

Routine implementation passes, bug fixes, and refactors — kept separate
from [`docs/ally_decision_log.md`](docs/ally_decision_log.md), which is
reserved for genuine "why we chose X over Y" design rationale. If an entry
here turns out to carry real architectural rationale in hindsight, move it
to the decision log instead of leaving it here.

---

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