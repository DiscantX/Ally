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
  