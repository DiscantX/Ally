# Ally

Ally is an AI game companion. It watches your screen (or reads a game's own
log/API where one exists), and plays along like a friend sitting next to you
on the couch — commentary, analysis, and suggestions, not a walkthrough.

It's built to be genre- and game-agnostic: adding a new screen-capture game
should require zero Python, just a config file and (optionally) a calibrated
layout. Tested so far against Slay the Spire, FTL, and Magic: The Gathering
Arena (MTGA).

For the founding intent behind this ("a friend that remembers," why
generalizability matters) see the archived original scope doc at
[`docs/archive/project_design_document_early.md`](docs/archive/project_design_document_early.md) —
most of its *mechanisms* are outdated, but the goals it describes still hold.

## How it works, briefly

```text
Collectors -> Scribe -> State Sandbox -> Entity Registry -> Memory Manager -> Ally -> Output
```

- **Collectors** get game state, either by screen capture + OCR (most games)
  or by reading a game's own structured log/API when one exists (MTGA).
- **Scribe** is a vision model whose only job is to describe what's on
  screen — it never interprets or suggests anything.
- **Ally** is a separate, air-gapped reasoning agent: it never sees the raw
  screenshot, only the facts the rest of the pipeline extracted this run.
  This is deliberate — see the decision log for why.

For the real architecture reference (current components, how they fit
together) see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Setup

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=your_key_here   # genai.Client() picks this up
```

Screen-capture play is Windows-only today (`pywin32`/`win32gui` for window
capture). MTGA's log-based Collector has no such dependency.

## Running it

```bash
# Live loop against a game window. Auto-creates configs/<game_id>/config.json
# from the currently focused window if it doesn't exist yet.
python main.py --game ftl

# Same, but derives game_id from whatever window is focused right now.
python main.py

# Explicit config path -- skips --game lookup/auto-create entirely.
python main.py --config configs/ftl/config.json

# Live loop with the Tkinter GUI overlay.
python main.py --gui

# Single-file mode, no loop -- useful for quickly testing the pipeline
# against a screenshot without a live game window.
python main.py images/monkey.png
```

The first run against a new game will feel rough: screens aren't calibrated
yet, so OCR runs uncalibrated and Scribe does more work per turn. Calibrate
HUD regions with `tools/inspect_coords.py`, or just keep playing — the
screen bootstrapper will draft layouts automatically after a few
unrecognized screens, with no manual step required. See
[`docs/adding_a_new_game.md`](docs/adding_a_new_game.md) for the full
walkthrough (not yet split out — until then,
`tools/init_config.py`, `tools/inspect_coords.py`, and
`collectors/configured_collector.py`'s module docstrings cover it).

## Tests

```bash
python -m unittest discover tests
```

See [`tests/README.md`](tests/README.md) for what each module covers.
MTGA-specific tests are separate — see
[`plugins/mtga/README.md`](plugins/mtga/README.md).

## Docs map

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — current components and
  how they fit together
- [`docs/ally_decision_log.md`](docs/ally_decision_log.md) — why things are
  built the way they are, append-only history of real decisions
- [`docs/adding_a_new_game.md`](docs/adding_a_new_game.md) — onboarding a
  new game (planned)
- [`docs/roadmap.md`](docs/roadmap.md) — open items and structural gaps
- [`CHANGELOG.md`](CHANGELOG.md) — routine implementation passes and bug
  fixes, separate from the decision log's design rationale
- [`plugins/mtga/integration_notes.md`](plugins/mtga/integration_notes.md) —
  MTGA-specific research notes and gotchas
- [`CLAUDE.md`](CLAUDE.md) — repo conventions for AI contributors
  (typing/Pylance, markdownlint)

## What's real vs. in progress

Real and exercised in play: Scribe/Ally air-gap, screen capture + calibrated
OCR + local screen classification, the auto-bootstrapping fallback for
uncalibrated screens, tiered narrative memory with cross-session summaries,
personality memory, the entity registry (fuzzy + exact-ID resolution), and
the MTGA log-based Collector (parser, resolver, enum tables).

For what's still in progress or open, see [`docs/roadmap.md`](docs/roadmap.md)
— that's the maintained, canonical list. This section is a quick-glance
snapshot of what's solid, not maintained turn-by-turn.