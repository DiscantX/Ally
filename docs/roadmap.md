# Ally — Roadmap

> **Status: living reference.** Open items and structural gaps, kept
> current — not a history of what was decided or why (see
> [`ally_decision_log.md`](ally_decision_log.md) for that) and not a log of
> what already shipped (see [`CHANGELOG.md`](../CHANGELOG.md) for that).
> Items move here when identified, and out when resolved — remove an item
> once it's done rather than marking it "done" in place, so this list
> always reflects only what's actually still open.

## Open design questions

- `Collector` interface design refinements — OCR/CV pipeline for
  Mitigation 4 (visual masking) is still only partially explored.
- SQLite schema evolution for cross-run persistence of narrative memory,
  entity registry, and personality tiers, as real playtesting surfaces
  new access patterns.
- Tuning the `difflib` entity-resolution match threshold, or replacing it
  with embeddings, once real playtesting surfaces aliasing failures (see
  the decision log's Entity Registry section for why this was deferred
  rather than built day one).
- GUI/frontend stack — Tkinter is what's built; whether a local web
  frontend is worth building instead remains undecided.
- `entity_type` is hardcoded to `"unknown"` for every entity the Scribe
  path creates (MTGA's resolved-card path is the one exception today).
  This blocks future importance/salience scoring (the "Amygdala-analogy"
  component from the brain-analogy discussion) from distinguishing
  "player character" from "background prop" without either the Scribe
  emitting a real type field or a cheap heuristic in the registry.
- Thinking-amount control (`thinking_level`) for Interactions API: while thinking summaries work with `generation_config={"thinking_summaries": "auto"}`, explicit thinking budget/level config mapping on Interactions API should be re-verified as Google documentation matures.

## In progress / not yet fully wired

- **MTGA dispatch wiring.** `plugins/mtga/parser.py` and
  `plugins/mtga/resolver.py` are built and independently tested; the
  `build_collector` dispatch that actually routes `"mtga_log"` to an
  `MTGACollector`, and the `main.py`-level handling of a Collector that
  blocks on new log lines rather than polling, are not yet in place. See
  `plugins/mtga/integration_notes.md` §5–6.
- **MTGA's Ally-facing prior-knowledge prompt question.** The original
  "amnesiac walkthrough" framing doesn't map cleanly onto MTG — the real
  risk is Ally reciting known-optimal lines instead of behaving like a
  companion discovering the game. Needs its own prompt-design pass, not
  just a reuse of the existing air-gap framing.
- **SSIM threshold tuning**, both anchor-based (`ScreenClassifier`'s
  `match_threshold`) and whole-frame draft matching
  (`draft_match_threshold`) — currently tuned by observation during real
  playtesting (see `vision/screen_classifier.py`'s module docstring), not
  measured against a systematic capture-session dataset.
- **Auto-selecting a discriminating anchor region** for bootstrapped
  screens — currently `ScreenBootstrapper` uses whole-frame SSIM as its
  classification signature since picking a good, automatically-selected
  distinguishing sub-region is a harder vision problem, deferred.
- **Medium- and long-term memory flush**, while implemented
  (`NarrativeMemoryManager.flush_to_long_term`, `close_run`), is not yet
  extensively playtested at scale — real flush cadence and summary
  quality over a long run remain largely unverified.
- **Knowledge-graph-style entity relationships** — `EntityRegistry` today
  is a flat append-only store per entity; no relationship modeling
  between entities exists yet.
- **Embedding-based entity resolution** — the seam exists
  (`EmbeddingProvider`/`VectorIndex` interfaces with null defaults, per
  the decision log's Embeddings section) but nothing plugs into it; the
  registry still resolves purely via `difflib` (or exact `external_id`
  matching, where a Collector supplies one).
- **`perspective_keywords.json` keyword tuning** — [`perspective_keywords.json`](configs/template/perspective_keywords.json:1) keyword lists are an untuned first pass expected to need adjustment against real gameplay across various games.

## Deferred by explicit decision (not forgotten, not scheduled)

- A local image-embedding similarity gate above SSIM+ROI masking, for
  catching semantically novel content (e.g. a popup outside any
  calibrated region) that motion masking can't. Revisit only if
  SSIM+ROI is shown to under- or over-trigger in real playtesting.
- Replacing the Scribe itself with a local vision model — larger scope
  than turn-gating, and matching Scribe's structured-output quality on
  target low-end-PC hardware is an open question in its own right.
- Auto-promotion of a CLIP-learned `"normal"` screen category to
  `"low_value"` — a repetition/staleness heuristic risks silently gating
  real gameplay without real playtesting data to tune it against.