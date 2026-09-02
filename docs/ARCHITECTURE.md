# Ally — Architecture

> **Status: living reference.** This document is edited in place to reflect
> the system as it currently exists — not a history of how it got here. For
> *why* something was built the way it was, see
> [`ally_decision_log.md`](ally_decision_log.md). For what's planned but not
> yet built, see [`roadmap.md`](roadmap.md).

## 1. Overview

Ally is an AI game companion built around one non-negotiable constraint: the
agent that talks to the player (**Ally**) never sees a raw screenshot. A
separate perception agent (the **Scribe**) looks at the screen and reports
only extracted facts; Ally reasons from those facts alone. This air-gap
exists so that a model's prior training-data knowledge of a given game can't
leak into its commentary — Ally is meant to discover the game alongside the
player, not recite a walkthrough it already knows. The pipeline is
deliberately genre- and game-agnostic: onboarding a new screen-capture game
should require zero Python (a config file, plus an optional calibrated
layout), and a game with its own structured data source (MTGA's log) plugs
in as an alternate Collector rather than forcing everything through
screenshots.

## 2. Pipeline Diagram

Two Collector shapes feed the same downstream pipeline. Most games go
through screen capture + OCR; a game with its own structured log/API (MTGA
today) bypasses the Scribe almost entirely, since its data arrives as exact
state rather than pixels to interpret.

```text
                         ┌───────────────────────────┐
                         │         Collectors         │
                         │  (pluggable capture layer)  │
                         └──────────────┬──────────────┘
                                         │
                    ┌────────────────────┴────────────────────┐
                    │                                          │
        screen + OCR path                         structured-log/API path
    (GenericHudCollector, most games)                  (MTGALogParser, MTGA)
                    │                                          │
                    ▼                                          │
     ┌──────────────────────────┐                              │
     │  Superior Colliculus      │                              │
     │  (ChangeDetector: SSIM     │                              │
     │  frame-diff gate, ROI      │                              │
     │  masking)                  │                              │
     └──────────────┬─────────────┘                              │
                     ▼                                           │
     ┌──────────────────────────┐                              │
     │  ScreenClassifier          │                              │
     │  (anchor/draft SSIM match   │                              │
     │  → which layout + prompt    │                              │
     │  mode to use)                │                              │
     └──────────────┬─────────────┘                              │
                     ▼                                           │
     ┌──────────────────────────┐                              │
     │  LayoutOCRReader            │                              │
     │  → ConfirmedFacts            │                              │
     │  (calibrated regions only)    │                              │
     └──────────────┬─────────────┘                              │
                     ▼                                           │
     ┌──────────────────────────┐                              │
     │  Scribe (Gemini vision)     │                              │
     │  → ScreenElements,            │                              │
     │  screen_name_guess,            │                              │
     │  genre_guess                    │                              │
     │  (skipped if ScreenBootstrapper  │                              │
     │  isn't needed and skip_ally is   │                              │
     │  set by the semantic diff guard) │                              │
     └──────────────┬─────────────┘                              │
                     │                                           │
                     └─────────────────┬─────────────────────────┘
                                        ▼
                        ┌───────────────────────────┐
                        │        StateSandbox         │
                        │  current_elements (Scribe)   │
                        │  confirmed_facts (OCR)         │
                        │  structured_state (MTGA, etc.)  │
                        └──────────────┬───────────────┘
                                        │
                     ┌──────────────────┼──────────────────┐
                     ▼                  ▼                  ▼
          ┌───────────────┐  ┌──────────────────┐  ┌───────────────┐
          │ EntityRegistry  │  │  GenreTracker      │  │ MemoryManager   │
          │ (fuzzy + exact-  │  │  (accumulates,      │  │ (short/medium/   │
          │  id resolution)   │  │  locks on threshold)  │  │  long-term +      │
          └───────┬─────────┘  └──────────┬─────────┘  │  personality)      │
                   │                        │            └────────┬─────────┘
                   └────────────┬───────────┘                     │
                                ▼                                  │
                     ┌────────────────────────────────────────────┘
                     ▼
          ┌───────────────────────────┐
          │            Ally             │
          │  (Gemini reasoning; never    │
          │  sees the raw screenshot)     │
          │  → analysis, actions,          │
          │  run_boundary                    │
          └──────────────┬────────────────┘
                          ▼
              ┌───────────────────────┐
              │        Output           │
              │  (GUI overlay / log /    │
              │  chat response)            │
              └───────────────────────┘
```

Notes on what this diagram simplifies:

- **The MTGA path is drawn as intended, not as fully wired today.** The
  parser/resolver/enum-table pieces are built and tested standalone; the
  dispatch wiring that lets `build_collector` actually route to
  `MTGACollector` (and the `main.py`-level handling of a Collector that
  blocks on new log lines rather than polling) is still in progress. See
  `roadmap.md`.
- **Superior Colliculus, ScreenClassifier, and the OCR reader are all
  screen-capture-specific** — a structured-log Collector like MTGA's has no
  equivalent step; it hands `StateSandbox` a `structured_state` payload
  directly.
- **`skip_ally`** is a semantic diff guard: even when pixel-level motion
  fires the change detector, if this turn's `ConfirmedFacts` are identical
  to last turn's, the Scribe/Ally calls are skipped and only state
  bookkeeping happens — shown above as a parenthetical on the Scribe box
  rather than its own component, since it's a control-flow shortcut, not a
  pipeline stage.
- **`ScreenBootstrapper`** isn't shown as its own box — it fires
  conditionally (three consecutive "unknown" classifications) off the same
  Scribe call already happening that turn, drafting a new layout rather than
  sitting in the main line of data flow.

---

## 3. Component Glossary

Current-state descriptions only — for rationale behind a design choice, see
the decision log entry linked at the end of each subsection where one
exists.

### Collection

**`ScreenCollector`** ([`ingestion/collectors/screen_collector.py`](../ingestion/collectors/screen_collector.py:1))
Wraps window capture (`ClientRect`/`win32gui`) and `mss` screen-grabbing into
a single `capture()` call. Returns a `RawObservation` with a PIL image, and
runs the `ChangeDetector` internally to set `RawObservation.changed`.
Windows-only today; deliberately the *only* place that knows about
`win32`/`mss`, so a future non-Windows backend is a one-file swap.

**`GenericHudCollector`** ([`ingestion/collectors/configured_collector.py`](../ingestion/collectors/configured_collector.py:1))
The default Collector for any screen-capture game. Composes
`ScreenCollector` + `ScreenClassifier` + a dict of `LayoutOCRReader`s (one
per named screen) + `ScreenBootstrapper`, all driven by a small
`CollectorConfig` (window title, layout directory, source tag) loaded from
`configs/<game_id>/config.json`. Adding a new screen-capture game requires
zero custom Python — see §5, Extension Points.

**`MTGALogParser`** ([`ingestion/plugins/mtga/parser.py`](../ingestion/plugins/mtga/parser.py:1))
The structured-log alternative to screen capture. Tails MTGA's `Player.log`
via `LogReader`, parses framed GRE JSON payloads, and accumulates a running
`game_state` dict by applying `GameStateType_Full`/`GameStateType_Diff`
messages and their `annotations`. Resolves card/token identity through
[`ingestion/plugins/mtga/resolver.py`](../ingestion/plugins/mtga/resolver.py:1) (`EntityResolver`, `EnumResolver`) against
Arena's own local SQLite card database. See
[`plugins/mtga/integration_notes.md`](../plugins/mtga/integration_notes.md)
for the full data-source evaluation and message-format details.

**`LogReader`** ([`ingestion/collectors/log_reader.py`](../ingestion/collectors/log_reader.py:1))
Generic, game-agnostic log-tailing utility — not MTGA-specific despite
being introduced for it. Supports one-shot replay (`follow=False`, used for
fixture-based tests) and live tailing (`follow=True`), with
`start_at_end` controlling whether a live tail replays existing content
first. Detects file truncation/restart via inode identity, so a Collector
tailing a log that gets overwritten at session start (as MTGA's does)
recovers cleanly instead of hanging or reading garbage.

**`ChangeDetector`** ("Superior Colliculus", [`brain/perception/change_detector.py`](../brain/perception/change_detector.py:1))
Pre-Scribe frame-diff gate deciding whether a turn is worth processing at
all. Defaults to SSIM comparison (falls back to raw `absdiff` if
scikit-image is unavailable) for reduced sensitivity to ambient
texture/brightness churn. Supports ROI masking (`set_ignore_regions`) so
layout elements flagged `ignore_motion: true` — animated backgrounds,
particle effects — are zeroed out of the diff rather than needing a global
threshold tuned around them. Also implements a stability check (waits for
a transition to *settle* before firing) and a cooldown window after a major
change, to avoid firing mid-transition or re-firing immediately after a
big trigger.

### Vision / Screen Identification

**`ScreenClassifier`** (`vision/screen_classifier.py`)
Identifies which named screen (combat, map, shop...) the current frame
shows, using local SSIM image comparison — no API call, no per-turn lag.
Two match tiers: **anchor matching** (a manually calibrated, distinctive
box compared against a reference crop — precise) and **draft matching**
(whole-frame SSIM against a bootstrapped screen's reference frame — coarser,
used before any anchor exists for that screen). Runs before the Scribe
every turn, since its result determines both which `LayoutOCRReader` to use
and which Scribe prompt variant (UI vs. NO_UI) to send.

**`ScreenBootstrapper`** (`vision/screen_bootstrapper.py`)
Closes the loop on unrecognized screens with no human step. Triggers after
`unknown_streak_threshold` consecutive "unknown" classifications; drafts a
new `layouts/<screen>.json` from that turn's already-computed Scribe output
(name from `screen_name_guess`, candidate boxes from `screen_elements`).
Each drafted box self-confirms via `vision.ocr.looks_like_real_text()`
rather than waiting on manual review. `tools/inspect_coords.py` remains
available for a human to clean up a draft afterward, but nothing blocks on
that happening.

**`LayoutManager` / `LayoutOCRReader`** (`vision/layout.py`,
`vision/layout_reader.py`)
`LayoutManager` loads a screen's calibrated `layout.json` into `UIElement`s
(pixel box + OCR hints + trust flags). `LayoutOCRReader` reads every
*trusted* element with Tesseract each turn and returns `ConfirmedFact`s. An
element is trusted if it's human-calibrated, or if it's a `scribe_auto`
draft that passed self-confirmation; `is_anchor` elements are never OCR'd
(they exist only for `ScreenClassifier`).

### State

**`StateSandbox`** (`state/sandbox.py`)
The per-turn fact store Ally ultimately reads from (via `as_context()`).
Holds three kinds of data with distinct trust/lifecycle framing:
`current_elements` (Scribe's interpretation, fully overwritten every turn),
`confirmed_facts` (OCR or any Collector-supplied exact reading, also fully
overwritten every turn), and `structured_state` (e.g. MTGA's accumulated
game state — persists across turns when a turn's `update()` call omits it,
since the owning Collector maintains it as a running accumulation, not a
per-turn replay). See §4 for the full trust-framing rationale.

**`EntityRegistry`** (`state/entity_registry.py`)
Non-lossy, append-only memory of everything seen this run. Two resolution
strategies chosen per-element: **fuzzy** (`difflib` string matching against
known names/aliases — the default, for Scribe's free-text labels) and
**exact** (skips fuzzy matching entirely when a Collector supplies an
`external_id`, e.g. MTGA's `instanceId` — via `_external_id_index` for O(1)
lookup). `entity_type` defaults to `"unknown"` unless a Collector supplies a
real one (MTGA's resolved card `type` does; Scribe's `ScreenElement` path
doesn't). Persisted per `(player_id, game_id, save_id)` via `MemoryDB`.

**`GenreTracker`** (`state/genre_tracker.py`)
Accumulates the Scribe's per-turn genre guess into a stable running best
estimate, locking once confidence clears a threshold. Deliberately kept
outside `StateSandbox` (which is fully overwritten every turn) so one
ambiguous frame — a cutscene, an establishing shot — can't regress an
otherwise-confident genre read.

### Reasoning

**`Scribe`** (`interpretation/scribe.py`)
Pure perception agent (Gemini vision). Given a screenshot, returns a
`ScribeOutput`: `screen_elements` (id/label/description/box_2d, with a
verbatim-transcription rule for on-screen text), plus `genre_guess` and
`screen_name_guess`. Two prompt modes — `SCRIBE_PROMPT_UI` (full element
extraction, used for uncalibrated screens) and `SCRIBE_PROMPT_NO_UI` (scene
entities only, used once a screen's layout is calibrated and OCR already
owns HUD values). Never interprets, never suggests actions, never told what
game it's looking at.

**`Ally`** (`ally/ally_agent.py`)
The reasoning/personality agent (Gemini). Air-gapped from the raw
screenshot by construction — `decide()` and `chat()` only ever receive text
context assembled by `StateSandbox`, `EntityRegistry`, `GenreTracker`, and
`MemoryManager`. Returns an `AllyOutput` (natural-language `analysis`, a
list of candidate `ActionItem`s, and a `run_boundary` signal) or, for
player-initiated chat, an `AllyChatOutput`. This split is the architectural
core of the project — see the decision log's "Air-gap" section for why.

**Personalities** (`ally/personalities.py`)
A dict of named, second-person personality descriptions (`PERSONALITIES`)
injected into Ally's prompt to shape tone and voice. `"Scout"` is the
current default. Selected once per run (`personality_name` on `AllyCore`)
and layered under whatever `MemoryManager.get_personality_context()`
returns, once personality memory has accumulated enough to redistill past
the base description.

### Memory

**`MemorySystem` / `MemoryManager`** (`memory/manager.py`)
Coordinator unifying `NarrativeMemoryManager` and `PersonalityMemoryManager`
under one lock-guarded interface, backed by `MemoryDB` (SQLite). Exposes
`record_turn`, `build_context`, `get_personality_context`,
`flush_to_cross_session`, and `close_run`.

**`NarrativeMemoryManager`** (`memory/narrative.py`)
Tiered, lossy compression pipeline: short-term rolling buffer
(`deque(maxlen=N)`) → medium-term situational summaries → long-term
strategic summary → cross-session summary (on run close). Each tier is
populated by an LLM summarization call from the tier below it. Flush
timing is driven by a `CompositeTrigger` (turn-count interval, salience
threshold, or an explicit checkpoint) rather than turn count alone.

**`PersonalityMemoryManager`** (`memory/personality.py`)
A separate, slower-moving multi-resolution store for Ally's
personality/player-relationship memory, keyed by `player_id` alone (not by
game — Ally is meant to feel like the same friend across different games).
Master journal (append-only, never rewritten) → Digest (~200–400 words) →
Micro (<50 tokens, injected into every prompt). Fully regenerates digest
and micro from the master journal on each `redistill()` call.

**`SaveTracker`** (`memory/save_tracker.py`)
Resolves whether to resume an open `save_id` or start a new one, using an
idle-window heuristic (default 2 hours) against `last_active_at`. Also
provides the collector-native override seam (`RawObservation.run_started` /
`run_ended`) alongside `AllyOutput.run_boundary` for semantic
run-boundary detection — see `memory/triggers.py`'s `resolve_run_ended`
for the priority order between the two signals.

### Orchestration

**`AllyCore`** (`ally/core.py`)
GUI-agnostic central manager. Owns the Scribe, Ally, `StateSandbox`,
`GenreTracker`, `MemoryManager`, `EntityRegistry`, and active Collector;
drives `run_turn()` (one full pipeline pass) and `run_loop()` (continuous
polling loop with run-boundary handling). Exposes observer-style callback
hooks (`on_status_update`, `on_feedback`, `on_chat_message`, etc.) so
frontends — the Tkinter overlay, a headless terminal run, tests — attach
without `AllyCore` knowing anything about them. `send_message()` handles
player-initiated chat/feedback on a background thread, guarded by the same
`state_lock` `run_turn()` uses.

**`main.py`**
Entry point. Resolves a config path (explicit `--config`, `--game` lookup
with auto-create via `cabinet/configs/init_config.py`, or single-image back-compat
mode), constructs `AllyCore`, and either launches the Tkinter overlay
(`--gui`) or runs headless with `log()`-based callback wiring.

### Plugins

A **plugin** (a bespoke Collector implementation living under
`plugins/<game>/`) is the fallback extension mechanism, reserved for a game
whose data doesn't fit the "screenshot + calibrated OCR" shape that
`GenericHudCollector` handles. `build_collector`'s `collector_type` field is
the dispatch seam for this (`"screen_ocr"` today; a future `"mtga_log"`
value routes to a plugin's Collector once wiring is complete). The concrete
worked example is `plugins/mtga/` — MTGA's own structured log stands in for
what the original design doc called a `CommunicationMod`-style internal
API. Plugins do not get any special access to Ally's reasoning; they only
ever supply data through the same `Collector`/`RawObservation` contract
every other Collector uses. For MTGA specifically, see
[`plugins/mtga/integration_notes.md`](../plugins/mtga/integration_notes.md)
and [`plugins/mtga/README.md`](../plugins/mtga/README.md).

## 4. Data Flow Contracts

### The Collector contract

Every Collector (`collectors/base.py`) — screen-capture or structured-log —
produces a `RawObservation`: a PIL image (or `None`, e.g. when the window
isn't focused) plus zero or more `ConfirmedFact`s. A `ConfirmedFact` is a
`(key, value, source)` triple representing something read with certainty,
bypassing the Scribe entirely — calibrated OCR is the common case today, but
the contract doesn't care how the fact was obtained. This is what lets
`StateSandbox` treat OCR-derived values and Scribe-derived values with
different trust levels without knowing anything about how either was
produced.

### Two bounding-box formats, one conversion point

Two incompatible box formats exist in the pipeline, and every call site
converts explicitly through `vision/geometry.py` rather than assuming one
means the other:

- **Scribe's format** (`ScreenElement.box_2d`): `[y_min, x_min, y_max,
  x_max]`, normalized 0–1000, relative to the full frame — Gemini's native
  output shape.
- **Calibrated layout format** (`vision.layout.UIElement`, `layout.json`):
  absolute pixel `x, y, w, h`, relative to the captured window's client
  area — what Tesseract needs for an exact crop.

`normalized_box_to_pixels()` and `pixels_to_normalized_box()` are the only
two functions that cross this boundary. Both `ScreenBootstrapper` (Scribe
boxes → draft layout boxes) and `tools/inspect_coords.py`'s Scribe-seeding
path go through here.

### Three kinds of per-turn data, three trust framings

`StateSandbox` (`state/sandbox.py`) is deliberately dumb — it holds what was
handed to it, decides nothing. What it holds falls into three categories
with different lifecycle and trust semantics, and `as_context()` presents
each to Ally with language that reflects that difference:

| Field | Source | Lifecycle | Trust framing |
| --- | --- | --- | --- |
| `current_elements` | Scribe's `screen_elements` | Fully overwritten every turn | An LLM's interpretation of an image — presented as such |
| `confirmed_facts` | Calibrated OCR, or any Collector-supplied exact reading | Fully overwritten every turn | "Confirmed exact readings... trust these" |
| `structured_state` | A Collector's own accumulated state (e.g. MTGA's parsed `game_state`) | **Persists across turns** when a turn's `update()` call omits it | At least as trustworthy as confirmed facts — not a crop-and-recognize step over pixels at all |

The `structured_state` persistence rule is the one non-obvious part: unlike
the other two fields, it is *not* reset to `None` just because a given
turn's `update()` call didn't pass one. This is what lets a Collector like
`MTGALogParser` hand `StateSandbox` a reference to its running accumulation
only when something actually changed, rather than replaying the full game
state every single turn the way Scribe's elements are replayed.

A calibrated `ConfirmedFact` being "trusted" is a statement about
cost/reliability, not about human verification specifically — see
`LayoutOCRReader`/`vision/layout.py`'s `is_trusted` property. A
human-calibrated box and a `scribe_auto` draft that self-confirmed via
`looks_like_real_text()` are both trusted the same way; calibration is
today's mechanism for establishing that trust, not a requirement baked into
the data model itself.

## 5. Extension Points

### Adding a screen-capture game: config-first, zero Python

The default and preferred path for any new game that's played by looking at
a window:

1. **` cabinet/configs/init_config.py`** — run against the game's focused window (or
   invoked automatically by `main.py --game <id>` when no config exists
   yet). Auto-generates `configs/<game_id>/config.json` (window title,
   layout directory, source tag) purely from convention — no manual editing
   required to get a game running for the first time.
2. **Play.** With no calibrated layout yet, every screen runs Scribe in
   full-UI mode and produces no `ConfirmedFact`s — this is an expected,
   non-fatal state, not an error condition.
3. **Calibration happens automatically or manually, at your discretion.**
   `ScreenBootstrapper` drafts layouts on its own after a few consecutive
   unrecognized screens (see §3). `tools/inspect_coords.py` remains
   available any time for a human to hand-calibrate a screen or clean up a
   bootstrapped draft, but nothing in the pipeline blocks on that happening.

No custom Python class is required anywhere in this path.

### Adding a structurally different game: the plugin fallback

A plugin (`plugins/<game>/`, a bespoke `Collector` implementation) is
reserved for a game whose data doesn't fit "screenshot + calibrated OCR" at
all — the concrete case is a game with its own structured log or API
(MTGA's `Player.log`, or the original design doc's `CommunicationMod`-style
example). `collectors/configured_collector.py`'s `build_collector()`
dispatches on a `collector_type` field in the config (`"screen_ocr"` today;
a future `"mtga_log"` value routes to a plugin's Collector once that wiring
is complete) — this is the seam a new structurally-different game hooks
into. A plugin only ever supplies data through the same
`Collector`/`RawObservation` contract every other Collector uses (see §4);
it gets no special access to Ally's reasoning. See §3's Plugins entry and
`plugins/mtga/integration_notes.md` for the worked example.

### Experimental, not part of the core pipeline

`goodies/geneology.py` is a standalone experiment that breeds new
`PERSONALITIES` entries together via an LLM call, producing fused
personas across simulated generations. It is not wired into `AllyCore` or
any live turn loop — nothing in the pipeline currently consumes its output.

## 6. Brain Analogy (trimmed)

Explored during design as a way to find missing components and get shared
vocabulary — not a design constraint. Biological fidelity was never a goal,
and not every component has a clean 1:1 mapping. Kept here only for
components that actually exist today; see `ally_decision_log.md` if you
want the fuller exploration, including the components this analogy
motivated that haven't been built.

| Ally component | Brain analogue | Fit |
| --- | --- | --- |
| Screenshot capture | Retina | Strong — raw transduction, no interpretation |
| Pre-Scribe change detection (`ChangeDetector`) | Superior colliculus | Strong — fast pre-cortical filter for "did anything change enough to bother looking closer" |
| Scribe | V1 → ventral stream (identity) + dorsal stream (location) | Strong — matches the `label`/`description` vs `box_2d` split exactly |
| State Sandbox | Sensory buffer / iconic memory | Moderate — a short-lived holding area between perception and working memory |
| Short-term narrative memory | Dorsolateral prefrontal cortex | Strong — working memory: limited capacity, actively maintained |
| `flush_*` compression calls | Hippocampus | Strong — the consolidation *mechanism*, not the storage site |
| Cross-session / long-term storage | Cerebral cortex (distributed) | Moderate — the resting place of consolidated memory |
| Entity Registry | Semantic memory | Moderate — facts about what things are, independent of the episode learned in |
| Ally | Prefrontal cortex | Strong — integrates perception, memory, and goals into decisions |
| Personality reflection/redistill | Default Mode Network + medial PFC | Strong — self-referential, autobiographical synthesis that runs "at rest," not during active play |

**Online vs. offline.** Task-Positive Network and Default Mode Network are
anti-correlated brain states, and that split maps cleanly onto a real
division the pipeline already has: **TPN ("online")** covers everything
that runs during a live turn — Scribe, Sandbox, short-term buffer, Ally
actively deciding. **DMN ("offline")** covers everything that runs between
turns or at session boundaries — the `flush_*` consolidation calls and
personality reflection/redistillation. This is why reflection and
redistillation deliberately run on a slower, separate cadence from the
active gameplay loop rather than inline with every turn.

## 7. Known Limitations

See [`docs/roadmap.md`](roadmap.md) for the current list of open items and
structural gaps.
