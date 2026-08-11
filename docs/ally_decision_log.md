# Ally — Decision Log

A running record of decisions made in design conversations, kept separate
from `project_design_document_early.md` (the original scope doc). That
doc describes the *space of options*; this doc tracks which ones we've
actually picked, and why, so future threads don't have to re-litigate
settled questions. Append new dated sections as decisions get made;
don't rewrite history here — if a decision changes, add a new entry that
supersedes the old one and say so explicitly.

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

Pipeline, in order:

``` Flowchart
Collectors -> Interpretation layer (Scribe) -> State Sandbox
    -> Memory Manager (parallel to Sandbox) -> Ally -> Output
```

- **Collectors** are pluggable (screen, `CommunicationMod`-style internal
  APIs, player text input) behind a common interface.
- **Interpretation layer** is where the Scribe and any OCR/CV
  preprocessing live. Strictly "observe and normalize," never "decide."
- **State Sandbox** is the authoritative, per-run fact store. Everything
  downstream reads from here, not from raw observations.
- **Memory Manager** persists across runs/sessions; sits alongside the
  sandbox, not inside it, since the sandbox is wiped/archived at run end
  and memory isn't.
- **Ally** is the only component that makes decisions and talks to the
  player.
- **Plugin system** only supplies game-specific collectors and parsing
  rules — it does not get to influence Ally's reasoning. This keeps the
  "fresh eyes" firewall intact.

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

```Flowchart
Short-term (rolling buffer)
  -> Medium-term (situational summary)
    -> Long-term (strategic summary, this run)
      -> Cross-session summary (on run close)
```

- Each tier is populated by an LLM summarization call from the tier
  below it — nothing skips a tier.
- **Short-term → medium-term:** flush every N events or N minutes,
  whichever comes first.
- **Medium-term → long-term:** triggered by narrative beats (location
  change, major state change) with a time-based fallback.
- **Long-term → cross-session:** triggered on run end.
- This pipeline is explicitly allowed to be lossy — it's for gist/
  narrative flow, not pointer facts. See Entity Registry below for the
  non-lossy counterpart.

### Personality: multi-resolution storage

Same distillation pattern, applied to personality, on a slower clock:

- **Master** — append-only journal, one entry per reflection pass, never
  rewritten or compressed. Ground truth; not sent to prompts directly.
- **Digest** (~200–400 words) — regenerated from master periodically;
  used for high-stakes/personality-forward prompts.
- **Micro** (<50 tokens) — regenerated from digest; injected into every
  prompt cheaply to keep voice consistent.
- Decided to start with **full regeneration** of digest/micro from
  source on each redistill (simpler, avoids drift) rather than
  incremental updates. Revisit only if token cost becomes a real problem
  in playtesting.

### Retrieval: recency-based for now

Decided **not** to use vector/semantic retrieval on day one. With a
small number of memory objects per tier, recency + explicit tier
boundaries is sufficient. See "Embeddings" below for the deferred
upgrade path and the hooks already built for it.

## Entity Registry

Added to solve a gap in the tiered memory design: lossy compression is
fine for narrative gist but loses concrete pointer facts (item names,
NPC identity) that must be recalled exactly. The registry is a second,
parallel memory type:

- **Non-lossy, append-only.** Facts about an entity are never rewritten
  or summarized away, only added to. Status/`last_seen` update instead.
- Persists for the whole run (not wiped like the short-term buffer);
  candidate for its own cross-session ("game knowledge") treatment later.
- Schema (see `state/entity_registry.py` in the vertical slice):
  `entity_id`, `entity_type`, `canonical_name`, `aliases`, `status`,
  `facts`, `first_seen`, `last_seen`, `importance`.
- Prompt inclusion is filtered by status/recency/importance, not dumped
  in full — a long RPG could accumulate hundreds of entities.

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
`llm/gemini_provider.py`, `interpretation/scribe.py`, `state/sandbox.py`,
`state/entity_registry.py`, `ally/ally_agent.py`, `main.py`.

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

### Mapping

| Ally component | Brain analogue | Fit |
| --- | --- | --- |
| Screenshot capture | Retina | Strong — raw transduction, no interpretation |
| Crop/filter before Scribe (Mitigation 4) | Thalamus | Strong — sensory gate, decides what reaches processing at all |
| (not yet built) pre-Scribe change detection | Superior colliculus | Strong — fast pre-cortical filter for "did anything change enough to bother looking closer" |
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
not yet built, added to open questions below.

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
- **Superior colliculus** (pre-Scribe change detector) — a near-free
  frame-diff style check deciding whether to invoke the Scribe at all
  on a given frame, rather than running full extraction every tick.
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
latency, and the raw absdiff ChangeDetector both false-triggered on
ambient motion (title-screen background animation) and under-triggered
on screen transitions (firing mid-transition instead of once settled).

Decided on a tiered stack of local, free signals, evaluated before ever
calling the Scribe:

1. **Stability check** (already built, was just never turned on) --
   ChangeDetector now runs with `enable_stability_check=True` by default
   from ScreenCollector, so a turn only fires once the screen stops
   moving, not on the first frame of a transition.
2. **ROI masking** -- layout.json elements can now carry an
   `ignore_motion` flag (calibrated the same way as `requires_hover`, via
   inspect_coords.py's new 'M' toggle). Plugins pass these regions into
   ChangeDetector.set_ignore_regions() so known-animated areas (title
   background, particle effects) are zeroed out of the diff entirely,
   rather than tuning a global threshold around them.
3. **SSIM over raw absdiff** -- ChangeDetector now defaults to
   structural similarity (skimage) instead of pixel-count absdiff, since
   it's far less sensitive to uniform texture/brightness churn while
   staying sensitive to actual structural change. Falls back to absdiff
   if scikit-image isn't installed.
   **Known gap, not yet resolved**: SSIM's percent scale is not
   comparable to the old absdiff percent scale -- threshold_percent /
   major_change_threshold / stability_threshold_percent were carried
   over from absdiff tuning and need to be re-measured against real
   capture sessions, not assumed correct.

Explicitly deferred, not rejected: a local image-embedding similarity
gate (small ONNX encoder, cosine similarity between frame embeddings) as
a further tier above SSIM+ROI, for catching semantically novel content
(a popup outside any calibrated region) that masking can't. Follows the
same "local model over API call" reasoning as the fastembed decision for
text embeddings. Not built -- revisit if SSIM+ROI still under- or
over-triggers in playtesting.

Also noted but not yet wired: LayoutOCRReader's ConfirmedFacts are
already computed locally every capture and currently discarded after
use each turn. Diffing this turn's ConfirmedFacts against last turn's
would be a free additional gate (did any calibrated value actually
change) but requires the collector to retain last turn's facts, which
it doesn't do yet.

Rejected direction, for now: replacing the Scribe itself with a local
vision model. Larger scope than the gating problem, and matching
Scribe's structured-output quality on target low-end-PC hardware is an
open question -- kept separate from turn-gating so the two decisions
don't get coupled.

## Plugin system re-scoped: config-first, plugins as true fallback

Reviewed what plugins/slay_the_spire/collector.py actually did and found
it contributed zero game-specific *logic* -- every behavior (window
capture, change detection, OCR, layout parsing) already lived in
collectors/ and vision/. The plugin class was three configuration values
(window title, layout path, source tag) wearing a Python-package
costume. This was caught before any layout.json was ever calibrated --
the OCR path this wrapped had not been exercised at all.

Decided: collapse per-game screen+OCR setup into a JSON config
(configs/<game>.json) consumed by one generic factory
(collectors/configured_collector.py: CollectorConfig, GenericHudCollector,
build_collector). Adding a new screen-capture game now requires zero
Python -- a config file and, whenever convenient, a calibrated
layout.json via inspect_coords.py. A missing/uncalibrated layout.json is
a non-fatal, logged state (empty ConfirmedFacts), not an error, since
this is expected during early integration of any new game.

This reaffirms and sharpens the earlier "plugins are a fallback, not the
default extension mechanism" position: a plugin (a bespoke Collector
class) is now reserved for a game that needs a structurally different
data path -- the concrete motivating case, per the original design doc,
is a CommunicationMod-style internal API returning exact GameState JSON
instead of pixels. build_collector's collector_type field is the seam
for that when it's actually needed; no game currently needs it, so it's
not built. plugins/slay_the_spire/ (including the dead duplicate
layout.py, since removed) has been deleted -- Slay the Spire is
currently just configs/slay_the_spire.json plus an as-yet-uncalibrated
layout.json.

## Screen-aware layouts + local screen classification

Extended layout calibration from one flat layout.json per game to one
per named screen (configs/<game>/layouts/<screen>.json), since HUD
element positions genuinely differ between e.g. combat and map screens
in most games.

Decided against having Scribe classify the current screen (rejected
alongside the earlier genre_guess-style approach considered for this):
would require either an extra API call per turn or a one-turn lag
reading last turn's classification. Instead: local anchor-based image
matching (vision/screen_classifier.py) -- a designated stable box per
screen, calibrated like any other box (inspect_coords.py's 'A' toggle),
compared via SSIM against the live frame each turn. No API call, no
lag, since it runs before Scribe and determines both which layout to
OCR against and which Scribe prompt to use.

This also finally activates the previously-dead SCRIBE_PROMPT_NO_UI:
a screen with a calibrated layout uses NO_UI (OCR already owns HUD
values, Scribe only extracts scene entities); an unrecognized/
uncalibrated screen falls back to SCRIBE_PROMPT_UI, same as before this
change, with box_2d now explicitly required to bound text only,
excluding any icon, since these boxes are also what inspect_coords.py's
Scribe-seeding path uses to draft new calibration.

Corrected framing from an earlier discussion: a calibrated layout's
ConfirmedFacts are trusted not because a human specifically verified
them, but because they're trusted enough to skip an API call in favor
of cheap local OCR. Human calibration is today's mechanism for
establishing that trust; an automated confidence score would serve the
same role if one existed later. StateSandbox's "confirmed exact
readings" framing should be read this way, not as a human-in-the-loop
requirement.

Deferred: calibration remains a manual, hidden-by-default fallback --
RawObservation.screen_name/screen_confidence are threaded through every
turn now so a "this screen is unrecognized" signal exists, but nothing
yet surfaces it to Ally or auto-triggers calibration. Natural next step
once real playtesting shows how often "unknown" actually comes up.

## Open questions for future threads

- `Collector` interface design (screen capture implementation, OCR/CV
  pipeline for Mitigation 4 — visual masking).
- SQLite schema for cross-run persistence of narrative memory, entity
  registry, and personality tiers.
- Concrete `MemoryManager` implementation (currently only designed on
  paper) and wiring it into Ally in place of `PERSONALITY_STUB`.
- Tuning the `difflib` match threshold, or replacing it with embeddings,
  once real playtesting surfaces aliasing failures.
- GUI/frontend stack — still undecided per the original scope doc
  (Tkinter vs. local web frontend).
- `entity_type` is hardcoded to "unknown" for every newly created entity since the Scribe doesn't currently classify type, that's expected, but it means your future importance/salience scoring (the Amygdala-analogy component) won't be able to distinguish "player character" from "background prop" without either the Scribe emitting a type field or a cheap heuristic in the registry.
