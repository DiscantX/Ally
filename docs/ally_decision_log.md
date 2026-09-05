# Ally — Decision Log

A running record of *why* decisions were made in design conversations —
kept separate from [`ARCHITECTURE.md`](ARCHITECTURE.md) (which describes
the system as it currently exists, not how it got there) and from
[`CHANGELOG.md`](../CHANGELOG.md) (which tracks routine implementation
passes and bug fixes, not design tradeoffs). This doc tracks which real
options got chosen, and the reasoning behind it, so future threads don't
have to re-litigate settled questions. Append new dated sections as
decisions get made; don't rewrite history here — if a decision changes,
add a new entry that supersedes the old one and say so explicitly.

For current component descriptions, the pipeline diagram, and data-flow
contracts, see [`ARCHITECTURE.md`](ARCHITECTURE.md). For open items and
structural gaps, see [`roadmap.md`](roadmap.md).

---

## Naming

- **Agent A = "Scribe."** Pure perception. Looks at the screenshot,
  extracts facts, never interprets, never suggests actions, has no
  personality.
- **Agent B = "Ally" itself**, not a separate "Player" agent. Ally is the
  reasoning/decision core — the thing with personality, memory, and a
  voice the human player talks to. It never sees the raw screenshot,
  only what the Scribe reported. This resolved naturally once we
  recognized personality and player-relationship memory obviously belong
  to Ally, not to an anonymous internal module.

## Overall architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the current pipeline diagram
and component breakdown. One rationale worth preserving here: the plugin
system was deliberately scoped to only ever supply game-specific
collectors and parsing rules — it does not get to influence Ally's
reasoning. This keeps the "fresh eyes" firewall (see Air-gap, below)
intact regardless of how a given game's data gets collected.

## Air-gap: Scribe/Ally split confirmed

Decided to implement the two-call air-gap (design doc's Mitigation 2)
rather than combining extraction and reasoning into one call, even for
the first vertical slice. Ally receives only the Sandbox's text summary
and Entity Registry context — never the image, never the Scribe's prompt.

## Memory system

### Scope: personality and player-relationship memory are global

Explicitly decided: personality and player-interaction memory are keyed
by `player_id` alone, not by game. Ally is meant to feel like the same
friend across different games. Cross-session *game knowledge* (facts
about a specific game learned across playthroughs) is a separate memory
type, keyed by `(player_id, game_id)`.

### Storage keys

- `player_id` → personality, player-interaction memory, cross-session
  game-knowledge memory (per game, but not tied to a specific save).
- `(player_id, game_id, save_id)` → run-specific short/medium/long-term
  narrative memory. Wiped/archived at run end; only its distillation
  survives upward.

### Narrative memory: tiered, lossy compression pipeline

Short-term → medium-term → long-term → cross-session, each tier populated
by an LLM summarization call from the tier directly below it — nothing
skips a tier (current implementation detail in
[`ARCHITECTURE.md`](ARCHITECTURE.md)'s `NarrativeMemoryManager` entry).
The flush cadence decisions:

- **Short-term → medium-term:** flush every N events or N minutes,
  whichever comes first.
- **Medium-term → long-term:** triggered by narrative beats (location
  change, major state change) with a time-based fallback.
- **Long-term → cross-session:** triggered on run end.
- This pipeline is explicitly allowed to be lossy — it's for gist/
  narrative flow, not pointer facts. See Entity Registry below for the
  non-lossy counterpart.

### Personality: multi-resolution storage

Same distillation pattern as narrative memory, applied to personality, on
a slower clock (master journal → digest → micro — see ARCHITECTURE.md for
the current tier sizes and regeneration mechanics). Decided to start with
**full regeneration** of digest/micro from source on each redistill
(simpler, avoids drift) rather than incremental updates. Revisit only if
token cost becomes a real problem in playtesting.

### Retrieval: recency-based for now

Decided **not** to use vector/semantic retrieval on day one. With a
small number of memory objects per tier, recency + explicit tier
boundaries is sufficient. See "Embeddings" below for the deferred
upgrade path and the hooks already built for it.

## Entity Registry

Added to solve a gap in the tiered memory design: lossy compression is
fine for narrative gist but loses concrete pointer facts (item names,
NPC identity) that must be recalled exactly. The registry is a second,
parallel memory type — non-lossy and append-only, persisting for the
whole run rather than being wiped like the short-term buffer. (See
ARCHITECTURE.md for the current schema.)

### Entity resolution strategy

- Classic coreference libraries (spaCy + coreferee, fastcoref) were
  investigated. Verdict: useful as a cheap, local, non-LLM preprocessing
  pass for **within-passage pronoun resolution** (cleaning up "he"/"her"
  in the Scribe's raw output), but they don't solve the actual hard
  problem — matching a new mention against a **growing cross-session
  entity database** is closer to record linkage than to coreference
  resolution as that field defines it. (`neuralcoref` is dead —
  unmaintained since 2019, avoid it.)
- Decided: first-pass resolution in the vertical slice uses `difflib`
  string matching against known names/aliases (zero dependencies, zero
  API calls). This will correctly miss real aliasing (e.g. "the
  lieutenant" vs "Marcus") — that's expected and is the concrete
  motivating case for the embedding upgrade below.
- The match step is deliberately isolated in code (marked with a `TODO`
  in `resolve_or_create`) so it can be swapped for embedding-based
  matching without touching the rest of the registry.

## Embeddings / vector search

Decided: **not a day-one dependency**, but build the seams now so it
drops in later without a rewrite.

- Two concrete use cases identified for later: (1) entity resolution at
  scale, once the active-entity list is too large to hand the LLM
  directly, and (2) semantic (relevance-based) memory retrieval, as an
  upgrade over recency-based retrieval.
- **Local embeddings are the preferred default**, not Gemini's API —
  driven by rate limits, real-time latency needs, and avoiding a network
  dependency for gameplay-critical calls. `fastembed` (ONNX, CPU,
  quantized small models — the same library Qdrant's own client bundles
  for local mode) is the concrete candidate; runs fine on a low-end PC.
- If/when Gemini embeddings are used: batch multiple texts into a single
  `batchEmbedContents` call rather than one request per item, to
  conserve the RPD budget. A separate async Batch API exists for
  high-volume background jobs (e.g. bulk re-embedding after a reflection
  pass) but isn't suitable for real-time lookups.
- Running two embedding models concurrently for extra quota headroom was
  considered and rejected as not worth the complexity (incompatible
  vector spaces, would need separate indexes) — batching already solves
  the RPD problem more simply.
- Architecture hooks decided now: `EmbeddingProvider` interface with a
  `NullEmbeddingProvider` default, `VectorIndex` interface (Qdrant or
  otherwise) with a `NullVectorIndex` default, and an optional
  `embedding: list[float] | None` field on stored records from the
  start so no schema migration is needed later. Qdrant's local mode
  (`QdrantClient(":memory:")` or `path=...`, no server/Docker required)
  is the concrete candidate for the vector index itself, rated for up to
  ~20,000 points — enough for a single player's store.

## JSON reliability

Decided to use `response_mime_type="application/json"` with a Pydantic
`response_schema` for all structured model calls, instead of asking for
JSON in the prompt text and parsing `response.text` directly. The
original prototype script did the latter and was exposed to markdown-
fence/stray-text parsing failures.

## Vertical slice (built)

First working skeleton, built from the original single-script prototype
(`image_test.py`), implementing: Collector (file-open stub) → Scribe →
State Sandbox → Entity Registry → Ally. Files: `schemas.py`,
`llm/gemini_provider.py`, `brain/perception/scribe.py`, `state/sandbox.py`,
`state/entity_registry.py`, `brain/reasoning/ally_agent.py`, `main.py`.

**Explicitly deferred in this slice** (not forgotten, just out of scope
for a first pass):

- No real `Collector` abstraction yet — `main.py` opens an image file
  directly rather than going through a `Collector` interface.
- No cross-run persistence — everything lives in memory for one run; no
  SQLite yet.
- No personality/memory system wired in — `PERSONALITY_STUB` is a
  placeholder for `MemoryManager.build_context()`.
- Entity resolution is `difflib`-only, per the decision above.

## Brain analogy

Explored as a way to find missing components and get shared vocabulary,
*not* as a design constraint — biological fidelity is not a goal, and
not everything has a clean 1:1 mapping. Where it's a strong structural
match it's noted below; where it's just a fun label, that's noted too.
See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the trimmed table covering
only components that exist today; the full table below includes
candidate components this analogy surfaced that aren't built yet.

### Mapping

| Ally component | Brain analogue | Fit |
| --- | --- | --- |
| Screenshot capture | Retina | Strong — raw transduction, no interpretation |
| Crop/filter before Scribe (Mitigation 4) | Thalamus | Strong — sensory gate, decides what reaches processing at all |
| Pre-Scribe change detection (built as `ChangeDetector`) | Superior colliculus | Strong — fast pre-cortical filter for "did anything change enough to bother looking closer" |
| Scribe | V1 -> ventral stream (identity) + dorsal stream (location) | Strong — matches the `label`/`description` vs `box_2d` split in the schema exactly |
| State Sandbox | Sensory buffer / iconic memory | Moderate — very short-lived holding area between perception and working memory, not IT cortex as originally guessed |
| Short-term narrative memory | Dorsolateral prefrontal cortex | Strong — working memory: limited capacity, actively maintained |
| `flush_*` compression calls | Hippocampus | Strong — the hippocampus is the consolidation *mechanism*, not the storage site |
| Cross-session / long-term storage | Cerebral cortex (distributed) | Moderate — the actual resting place of consolidated memory |
| Entity Registry | Semantic memory | Moderate — facts about what things are, independent of the episode learned in |
| Ally | Prefrontal cortex | Strong — integrates perception, memory, and goals into decisions |
| Personality reflection/redistill | Default Mode Network + medial PFC | Strong — self-referential, autobiographical narrative synthesis; runs "at rest," not during active play |
| (not yet built) fast action selection | Basal ganglia | See below |
| (not yet built) execution + error correction | Motor cortex + Cerebellum | See below |
| (not yet built) event importance tagging | Amygdala | See below |
| (not yet built) contradiction/uncertainty detection | Anterior cingulate cortex | Noted, lower priority |


### Online vs. offline: Task Positive Network / Default Mode Network

TPN and DMN are anti-correlated brain states — one suppresses the other.
This maps cleanly onto a split the design already had without naming it:

- **TPN ("online")**: Scribe, Sandbox, short-term buffer, Ally actively
  deciding — everything that runs during a live turn.
- **DMN ("offline")**: hippocampal consolidation (`flush_*`), personality
  reflection/redistillation — everything that runs between turns or at
  session boundaries.

This validates the existing decision to run reflection/redistill on a
slower, separate cadence from the active gameplay loop.

### New candidate components identified via this analogy

These are real, concrete design proposals the brain analogy surfaced —
not yet built. See [`roadmap.md`](roadmap.md) for current open items;
these are recorded here for the reasoning trail, not as a live task list.

- **Action Arbiter** (basal ganglia) — a fast, cheap action-selection
  layer between Ally's candidate actions and final output. Not an LLM
  call: a lookup/small learned model of
  `(situation-type, action-type) -> historical success rate`, updated
  from feedback (player accepted the suggestion, action succeeded).
  Lets routine/previously-solved situations skip full deliberation —
  a real latency/cost win, not just flavor.
- **Motor Cortex + Cerebellum** (execution + correction) — split into
  two pieces on purpose, matching the biology: a Motor Cortex/Effector
  that turns a symbolic action into a literal input event using the
  entity's `box_2d`, and a Cerebellum/corrector that compares the next
  Scribe read against the expected outcome and adjusts (misclick
  detection, coordinate drift correction).
- **Salience Scorer** (amygdala) — tags each event with an importance
  score at the moment it happens (boss fights, deaths, novel entities,
  recurring locations). Feeds directly into the existing but currently
  unset `importance` field on `Entity`, and biases what survives
  short-to-medium-term compression. This is the concrete mechanism for
  the original design doc's "tough battles and 'crazy' moments should
  persist."
- **Superior colliculus** (pre-Scribe change detector) — since built as
  `ChangeDetector`; see the Turn-gating section below and
  `ARCHITECTURE.md`.
- **Anterior cingulate cortex** (conflict/uncertainty detection) —
  flags contradictions (an entity's status changed unexpectedly, two
  actions score equally) and routes to "ask the player" instead of
  guessing. Lower priority than the above four.

### Naming convention decision

Decided **not** to name classes directly after brain regions
(`CerebralCortex`, `VentralStream`) as the primary class name, since the
mapping is intentionally loose in places and a literal name read out of
context could mislead a future reader about what the code actually does.
Instead: **functional names for classes/methods** (`ActionArbiter`,
`SalienceScorer`), **brain terms for module/package names and
docstrings**, where they're pure mnemonic value with no risk of
confusion — e.g. `basal_ganglia/action_arbiter.py`.

## Turn-gating: tiered signals before invoking Scribe/Ally

Problem: the flat capture-every-N-seconds timer was inducing needless
latency, and the raw absdiff `ChangeDetector` both false-triggered on
ambient motion (title-screen background animation) and under-triggered
on screen transitions (firing mid-transition instead of once settled).

Decided on a tiered stack of local, free signals, evaluated before ever
calling the Scribe (see `ARCHITECTURE.md`'s `ChangeDetector` entry for
the current mechanics of each tier):

1. **Stability check** — a turn only fires once the screen stops
   moving, not on the first frame of a transition.
2. **ROI masking** — layout elements can carry an `ignore_motion` flag so
   known-animated areas are zeroed out of the diff entirely, rather than
   tuning a global threshold around them.
3. **SSIM over raw absdiff** — far less sensitive to uniform
   texture/brightness churn while staying sensitive to actual structural
   change. Falls back to absdiff if scikit-image isn't installed.
   **Known gap, not yet resolved**: SSIM's percent scale is not
   comparable to the old absdiff percent scale — `threshold_percent` /
   `major_change_threshold` / `stability_threshold_percent` were carried
   over from absdiff tuning and need to be re-measured against real
   capture sessions, not assumed correct.

Explicitly deferred, not rejected: a local image-embedding similarity
gate (small ONNX encoder, cosine similarity between frame embeddings) as
a further tier above SSIM+ROI, for catching semantically novel content
(a popup outside any calibrated region) that masking can't. Follows the
same "local model over API call" reasoning as the fastembed decision for
text embeddings. Not built — revisit if SSIM+ROI still under- or
over-triggers in playtesting.

Also noted but not yet wired: `LayoutOCRReader`'s `ConfirmedFacts` are
already computed locally every capture and currently discarded after
use each turn. Diffing this turn's `ConfirmedFacts` against last turn's
would be a free additional gate (did any calibrated value actually
change) but requires the collector to retain last turn's facts, which
it doesn't do yet.

Rejected direction, for now: replacing the Scribe itself with a local
vision model. Larger scope than the gating problem, and matching
Scribe's structured-output quality on target low-end-PC hardware is an
open question — kept separate from turn-gating so the two decisions
don't get coupled.

## Plugin system re-scoped: config-first, plugins as true fallback

Reviewed what `plugins/slay_the_spire/collector.py` actually did and found
it contributed zero game-specific *logic* — every behavior (window
capture, change detection, OCR, layout parsing) already lived in
`collectors/` and `brain/perception/`. The plugin class was three configuration values
(window title, layout path, source tag) wearing a Python-package
costume. This was caught before any `layout.json` was ever calibrated —
the OCR path this wrapped had not been exercised at all.

Decided: collapse per-game screen+OCR setup into a JSON config
(`configs/<game>.json`) consumed by one generic factory
(`collectors/configured_collector.py`: `CollectorConfig`,
`GenericHudCollector`, `build_collector`). Adding a new screen-capture game
now requires zero Python — a config file and, whenever convenient, a
calibrated `layout.json` via `inspect_coords.py`. A missing/uncalibrated
`layout.json` is a non-fatal, logged state (empty `ConfirmedFacts`), not an
error, since this is expected during early integration of any new game.

This reaffirms and sharpens the earlier "plugins are a fallback, not the
default extension mechanism" position: a plugin (a bespoke Collector
class) is now reserved for a game that needs a structurally different
data path — the concrete motivating case, per the original design doc,
is a `CommunicationMod`-style internal API returning exact GameState JSON
instead of pixels. `build_collector`'s `collector_type` field is the seam
for that when it's actually needed; no game currently needs it, so it's
not built. `plugins/slay_the_spire/` (including the dead duplicate
`layout.py`, since removed) has been deleted — Slay the Spire is
currently just `configs/slay_the_spire.json` plus an as-yet-uncalibrated
`layout.json`.

## Screen-aware layouts + local screen classification

Extended layout calibration from one flat `layout.json` per game to one
per named screen (`configs/<game>/layouts/<screen>.json`), since HUD
element positions genuinely differ between e.g. combat and map screens
in most games.

Decided against having Scribe classify the current screen (rejected
alongside the earlier `genre_guess`-style approach considered for this):
would require either an extra API call per turn or a one-turn lag
reading last turn's classification. Instead: local anchor-based image
matching (`brain/perception/screen_classifier.py`) — a designated stable box per
screen, calibrated like any other box (`inspect_coords.py`'s 'A' toggle),
compared via SSIM against the live frame each turn. No API call, no
lag, since it runs before Scribe and determines both which layout to
OCR against and which Scribe prompt to use.

This also finally activates the previously-dead `SCRIBE_PROMPT_NO_UI`:
a screen with a calibrated layout uses NO_UI (OCR already owns HUD
values, Scribe only extracts scene entities); an unrecognized/
uncalibrated screen falls back to `SCRIBE_PROMPT_UI`, same as before this
change, with `box_2d` now explicitly required to bound text only,
excluding any icon, since these boxes are also what `inspect_coords.py`'s
Scribe-seeding path uses to draft new calibration.

Corrected framing from an earlier discussion: a calibrated layout's
`ConfirmedFacts` are trusted not because a human specifically verified
them, but because they're trusted enough to skip an API call in favor
of cheap local OCR. Human calibration is today's mechanism for
establishing that trust; an automated confidence score would serve the
same role if one existed later. `StateSandbox`'s "confirmed exact
readings" framing should be read this way, not as a human-in-the-loop
requirement.

## Coarse-grained synchronization

Decided to use a coarse-grained `threading.Lock` (`STATE_LOCK`) to
synchronize access to `sandbox`, `registry`, and `memory_manager`, rather
than fine-grained per-object locking. The project prefers simple,
obviously-correct mechanisms over complex fine-grained locking — this
approach directly addresses the concurrency issues in `main.py` and the
background GUI thread without the bug surface of finer-grained locking.
See [`docs/changelog.md`](docs/changelog.md) for the specific bug this surfaced and how it was
fixed during implementation.

## Personality Journal Triggers and Gameplay Writing

Decided to fix a major architectural oversight where personality journals and [`redistill()`](brain/memory/personality.py) were never updated during normal gameplay:

- **The bug**: [`redistill()`](brain/memory/personality.py) was previously only reachable via the single chat-feedback call site in [`AllyCore.send_message()`](brain/reasoning/ally_agent.py). Gameplay turns never wrote to the personality journal or triggered redistillation, meaning companion state in the UI never evolved during play unless the player manually submitted chat feedback.
- **The fix**: Gameplay now writes to the journal via a composite trigger (`TurnCountTrigger`, `SalienceEventTrigger`, and the new `SignificantMomentTrigger`), with journal-write frequency decoupled from redistill frequency (`personality_redistill_journal_interval`).
- **The bonus fix**: Wiring `significant_moment` into narrative's [`record_turn()`](brain/memory/narrative.py:1) call, activating its previously-dormant `SalienceEventTrigger` for genuinely significant turns.

## Perspectives, Scoring, and Streaming Thinking (Phase 2)

Decided on the design for competing internal psychological framings (Perspectives), local scoring heuristics, and diagnostic streaming thinking:

- **Perspectives vs. `PERSONALITIES`**: Kept strictly separate. A personality (see [`PERSONALITIES`](brain/reasoning/personalities.py:1)) is the stable voice Ally speaks in; a perspective (see [`PERSPECTIVES`](brain/reasoning/perspectives.py:10)) is an ephemeral internal pressure that rises and falls turn to turn (in the spirit of Disco Elysium's Thought Cabinet), which the active personality then mediates.
- **Perspective scoring design**: Implemented via [`PerspectiveEngine`](brain/reasoning/perspective_engine.py:41) as a text-based, local, zero-API-call heuristic operating on recent narrative buffer turns and entity facts. Deliberately avoids genre-specific numeric telemetry since Ally has no such thing across diverse games. Keyword lists live in [`perspective_keywords.json`](configs/template/perspective_keywords.json:1) for easy tuning without code changes.
- **Personality resolution style**: Decided against hardcoding behavior per personality entry; instead, personality evolution and nuance emerge naturally via [`redistill()`](brain/memory/personality.py:1) over the personality journal and narrative history.
- **Streaming-thinking design**: Implemented [`generate_structured_stream()`](infrastructure/llm/gemini_provider.py:147) as a separate provider method in [`GeminiProvider`](infrastructure/llm/gemini_provider.py:66). It follows Gemini's two-phase stream contract (all thought chunks `part.thought=True` first, all JSON content chunks `part.text` second). Because partial JSON is not valid JSON until the stream completes, `generate_structured_stream()` buffers content internally and parses only at the end. This method is diagnostic-only (used by [`perspective_thinking_diagnostic.py`](tooling/tools/perspective_thinking_diagnostic.py:1)); real-time JSON streaming remains deferred.

## Production Token-Level Streaming (Supersedes Earlier Non-Goal)

- **Supersedes**: This supersedes the earlier explicit non-goal in [`plans/CLAUDE_LED_TASK_personality_triggers_and_perspectives.md`](plans/CLAUDE_LED_TASK_personality_triggers_and_perspectives.md) §6, which stated that streaming would stay diagnostic-tool-only. That decision is reversed once the user confirmed they wanted live-streamed text in actual gameplay and chat.
- **Why a new provider method (`generate_structured_stream_field`)**: Solves a genuinely different problem than [`generate_structured_stream()`](infrastructure/llm/gemini_provider.py:147) (thinking-trace display vs. content-field display) and requires separate retry-and-reset semantics (reset callback to visibly clear stale partial text before a retry begins).
- **Mechanism (`partial-json-parser`)**: Raw JSON arrives incrementally from the SDK; [`partial-json-parser`](requirements.txt:14) extracts a named field's growing value from an incomplete buffer without abandoning `response_schema` validation for the final result.
- **Retry-and-reset design**: Mid-stream failures retry the whole call from scratch and visibly clear partial text first, ensuring retries never appear corrupted or duplicated.

## Migration to Gemini Interactions API (`client.interactions.create`)

- **Supersedes**: `GeminiProvider`'s use of `generateContent` as primary call surface.
- **Why**: Production thought-summary streaming never worked reliably after two implementation passes against `generateContent` + `response_schema` due to documented failure clusters where thought parts arrived without `part.thought` flag set or were omitted on low-complexity prompts. The Interactions API's dedicated `thought_summary` event type (`delta.type == "thought_summary"`) completely sidesteps flag-sniffing fragility.
- **Phase 0 Findings**: Verified against `google-genai==2.19.0`: `client.interactions.create(model=..., input=..., stream=True, response_format=..., generation_config={"thinking_summaries": "auto"})` successfully composes structured output and thinking summaries. Multimodal inputs (`[image, prompt]`) work correctly via `input=contents`.
- **Scoping**: Public method signatures on [`GeminiProvider`](infrastructure/llm/gemini_provider.py:66) (`generate_structured()`, `generate_structured_stream()`, `generate_structured_stream_field()`) were preserved exactly, ensuring all callers (`Scribe`, `Ally`, etc.) required zero changes.

## Provider-Agnostic LLM Base Interface + Thinking-Stream Parsing Fix

### Root Cause: Nested `delta.content.text` vs. Flat String

- **The bug**: For `thought_summary` deltas in the Interactions API stream, the actual thought text lives at `delta.content.text` — where `delta.content` is a **nested object** with its own `.type` and `.text` attributes, not a plain string.
- **The extraction code was**: `delta_text = delta_content if isinstance(delta_content, str) else (delta_text_attr if isinstance(delta_text_attr, str) else "")`
- **`isinstance(delta_content, str)` is `False`** for a `thought_summary` delta (it's an object), so this fell through to `delta.text`, which does not exist on thought_summary deltas. **Result: `delta_text` silently resolved to `""` for every thought chunk.**
- **This explains**: why text streaming worked fine (text deltas have `.text` at the delta level) but thinking never displayed.

### Fix Applied

- Created [`_iter_gemini_stream_events()`](infrastructure/llm/providers/gemini_provider.py:55) as the **single canonical place** that reads `delta.content.text` for thought_summary deltas.
- All streaming methods (`generate_structured_stream()`, `generate_structured_stream_field()`) now route through this generator — no method may read delta attributes directly anymore.

### Structured Output + Thinking Composition

- **Confirmed**: `response_format` (structured JSON schema) and `generation_config={"thinking_summaries": "auto"}` **compose correctly** — thought_summary deltas arrive even when strict schema is set.
- **Soft-schema workaround methods** (`generate_soft_structured_stream_field`, `generate_soft_structured_stream`) were removed as they are no longer needed once the parsing bug is fixed.

### Provider Interface Introduction

- **Created** [`LLMProvider`](infrastructure/llm/base_provider.py:74) abstract base class and [`RetryableProviderMixin`](infrastructure/llm/base_provider.py:58) for shared retry/backoff logic.
- **Provider-agnostic content types**: [`TextContent`](infrastructure/llm/base_provider.py:23), [`ImageContent`](infrastructure/llm/base_provider.py:28), [`Content`](infrastructure/llm/base_provider.py:31) dataclasses.
- **Moved**: `GeminiProvider` to [`infrastructure/llm/providers/gemini_provider.py`](infrastructure/llm/providers/gemini_provider.py:1), inheriting `LLMProvider` + `RetryableProviderMixin`.
- **Compatibility import**: [`infrastructure/llm/gemini_provider.py`](infrastructure/llm/gemini_provider.py:1) is now a thin re-export, keeping existing `from infrastructure.llm.gemini_provider import GeminiProvider` imports working unchanged.
- **Created** [`ProviderRouter`](infrastructure/llm/provider_router.py:10) (fallback + concurrent execution) with tests — not wired in this pass, exists as a tested seam for future fallback/A/B features.

### Decisions Not Made This Pass

- **`send_message()`'s chat path**: deferred decision on whether to adopt `previous_interaction_id` stateful mode for Ally's chat — ties reasoning to Gemini-specific threading, and Ally's context is synthesized fresh from StateSandbox/EntityRegistry/MemoryManager each turn.
- **`infrastructure/llm/model_lister.py`**: folded directly into [`infrastructure/llm/providers/gemini_provider.py`](infrastructure/llm/providers/gemini_provider.py:1) and eliminated as a separate root-level module, since model listing is 100% Gemini-specific.
- **OpenRouter provider**: designed for, not built.
---

## Thread Safety and Concurrency

### Coarse-grained synchronization strategy

**Decision**: Use coarse-grained locking (one lock per component) rather than fine-grained locking (separate locks for each data structure).

**Rationale**: 
- Simpler to reason about and less prone to deadlocks
- Performance impact is acceptable given the current scale (single-player, turn-based)
- Most operations are fast (dict lookups, list appends) - the lock contention is minimal
- Reduces cognitive overhead for future maintainers
- Matches the existing pattern already used in EntityRegistry

**Implementation**: Each major state-holding component gets its own `threading.RLock()`:
- `StateSandbox._lock` - protects turn-scoped state
- `EntityRegistry._lock` - protects entity resolution
- `MemoryDB._db_lock` - protects SQLite access
- `GenreTracker._lock` - protects genre estimation
- `ScreenCategoryStore._lock` - protects category matrix
- `AllyCore.state_lock` - protects core state
- `AllyCore._initialization_lock` - prevents race during startup
- `EventHook._subscriber_lock` (global) - protects subscriber list

### RLock over Lock

**Decision**: Use `threading.RLock` (reentrant lock) instead of `threading.Lock`.

**Rationale**: 
- RLock allows the same thread to acquire the lock multiple times without deadlocking
- This is essential when a method calls another method that also needs the lock
- Example: `AllyCore.send_message()` might call internal methods that also access `state_lock`
- Prevents subtle bugs where refactoring could introduce nested lock acquisition
- Minimal performance overhead for our use case

### Removing global STATE_LOCK

**Decision**: Remove the global `STATE_LOCK` from `main.py`. All thread synchronization now uses component-specific locks.

**Rationale**:
- Global lock was confusing - not clear what it was protecting
- Was inconsistently used (some code used it, some didn't)
- Created false sense of security - code that didn't use it had no thread safety
- Component-specific locks are more explicit about what they protect
- Easier to reason about lock ordering and deadlock prevention
- Each component manages its own synchronization boundaries

**Supersedes**: Earlier implicit assumption that a single global lock was sufficient for all thread safety needs.

### Thread-safe SQLite access

**Decision**: Use `check_same_thread=False` + application-level `RLock` for SQLite thread safety.

**Rationale**:
- SQLite connections are NOT thread-safe by default
- `check_same_thread=False` allows connections to be used from multiple threads
- Application-level lock (`MemoryDB._db_lock`) serializes all database access
- This is safer than connection pooling for our use case (single-player, moderate load)
- All 15+ database methods are wrapped with `with self._db_lock:`

**Alternatives considered**:
- Connection pooling: More complex, unnecessary for our scale
- One connection per thread: Wasteful, hard to manage
- SQLite WAL mode: Doesn't solve the fundamental thread-safety issue

### EventHook thread safety

**Decision**: Add global `_subscriber_lock` to make `EventHook.connect()`, `disconnect()`, and `emit()` thread-safe.

**Rationale**:
- EventHook is used across thread boundaries (background threads emit, main thread listens)
- Subscriber list modifications (connect/disconnect) must be atomic
- `emit()` makes a snapshot of subscribers list before iterating to avoid race conditions
- Global lock is appropriate here since EventHook is a singleton-style pattern

**Implementation**:
- `connect()`: acquires lock, appends to `_subscribers`
- `disconnect()`: acquires lock, removes from `_subscribers`
- `emit()`: acquires lock, makes copy of `_subscribers`, releases lock, iterates copy

### Qt-safe event dispatching

**Decision**: Create `QtSafeEventHook` wrapper for dispatching callbacks to Qt main thread.

**Rationale**:
- Qt GUI updates must happen on the main thread
- Background threads (LLM calls, screen capture) emit events that update the GUI
- Without this, GUI updates from background threads cause crashes or undefined behavior
- Uses `QMetaObject.invokeMethod()` with `Qt.QueuedConnection` for thread-safe dispatch

**Implementation**: 
- `QtSignalBridge` QObject with generic signal
- `QtSafeCallbackWrapper` wraps callbacks for Qt-thread invocation
- `QtSafeEventHook` wraps EventHook with Qt-safe dispatching
- Convenience function `connect_qt_safe()` for easy integration

### Initialization race condition fix

**Decision**: Add `_initialization_lock` and `_initialized` flag to `AllyCore` to prevent race conditions during startup.

**Rationale**:
- Multiple threads might call `initialize_run()` simultaneously
- Initialization involves creating MemoryManager, EntityRegistry, Collector
- These should only happen once
- Separate lock from `state_lock` to avoid deadlocks (run_loop might hold state_lock while initialize_run is called)

**Implementation**:
```python
with self._initialization_lock:
    if self._initialized:
        return
    # ... do initialization ...
    self._initialized = True
```

### EntityRegistry locking optimization

**Decision**: Use 4-phase locking strategy for `resolve_or_create()` to minimize lock hold time.

**Rationale**:
- Phase 1 (Read): Take snapshot of entities under lock
- Phase 2 (Process): Do CPU-intensive difflib matching WITHOUT lock
- Phase 3 (Write): Write results back under lock
- Phase 4 (DB): Write to database WITHOUT lock (MemoryDB has its own lock)

This reduces lock contention during expensive string matching operations while maintaining thread safety.

**Performance impact**: Significant for large entity sets, as difflib matching is CPU-bound and doesn't need the lock.

---

## Dev Inspector Theming and Views Foundation (Phase 1)

### Top-Level `theming/` Package
- **Decision**: Create a neutral top-level `theming/` package (`theming/color_convert.py`, `theming/palettes.py`) with zero PySide6 imports.
- **Rationale**: Both `infrastructure/logger/logger.py` and `interfaces/gui_qt/theming/theme.py` need shared access to palette data and color conversion utilities without creating cross-domain dependencies between infrastructure and interfaces.

### `NEUTRAL_CONTENT_THEME` Rename to `SLATE`
- **Decision**: Rename `NEUTRAL_CONTENT_THEME` to `SLATE` as a first-class user-selectable theme, while retaining `NEUTRAL_CONTENT_THEME = SLATE` as a deprecated compatibility alias.
- **Rationale**: Avoids breaking existing external imports while cleaning up nomenclature across dev panels and themes.

### Module Color Resolution Strategy
- **Decision**: Use exact dictionaries for `Slate` (`THEME_MODULE_COLORS`) and hashed-palette hue rotation (`THEME_MODULE_PALETTE_HUES`) for `Signal` and `Synthwave`.
- **Rationale**: Balances hand-curated exact color preservation for Slate (maintaining parity with legacy terminal colors) with automatic distinct color coverage for Signal and Synthwave themes.

### QSS Dynamic Property Selectors
- **Decision**: Use Qt dynamic properties (`QWidget[themed="..."]`) for QSS centralization across dev inspector panels, verified live in PySide6 `6.11.1`.
- **Rationale**: Qt's QSS engine reliably evaluates attribute selectors on dynamic properties, allowing centralized styling rules in `base.qss.tmpl` without hardcoding inline `setStyleSheet(...)` calls.

### Terminal Theme Hardcoding
- **Decision**: Terminal output intentionally remains hardcoded to the `"Slate"` palette in Phase 1; terminal theme switching is explicitly deferred.
- **Rationale**: Keeps scope focused on GUI dev inspector theming while providing a stable, fixed terminal palette.


