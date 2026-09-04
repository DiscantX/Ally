# Adding a New Game

> **Status: living reference.** How to onboard a game today. For *why* the
> onboarding flow is shaped this way, see
> [`ally_decision_log.md`](ally_decision_log.md)'s "Plugin system re-scoped"
> and "Screen-aware layouts" sections. For current component behavior, see
> [`ARCHITECTURE.md`](ARCHITECTURE.md).

Two paths, depending on how the game exposes its state:

- **Screen-capture + OCR** (almost every game) — zero Python required. This
  is the path this doc covers.
- **Structured log/API** (MTGA today) — needs a plugin, since the data
  isn't pixels at all. See §5 below if this is your situation.

If you're not sure which one applies: if the game has no modding API, no
log file exposing game state, and no equivalent of MTGA's `Player.log`,
you want the screen-capture path.

## 1. Quickstart

```bash
# Auto-creates configs/<game_id>/config.json from the currently focused
# window if it doesn't exist yet, then starts the live loop.
python main.py --game my_new_game

# Or skip --game entirely and let it derive game_id from whatever
# window is focused right now.
python main.py

# Add --gui-qt for the PySide6 overlay instead of terminal output.
python main.py --game my_new_game --gui-qt
```

The very first run needs the game's window focused and visible, since
`cabinet/configs/init_config.py` reads the focused window's title to generate
`configs/<game_id>/config.json` (window title, an empty `layouts/`
directory, a source tag — see `configs/template/config.json` for the
shape). `game_id` is derived by sanitizing the window title (lowercased,
non-alphanumeric runs collapsed to underscores) unless you pass one
explicitly via `--game`.

That's it — there is no second step required to get the pipeline running.
Everything below is either automatic, or optional manual calibration.

## 2. What happens automatically

With no calibrated layout yet, every screen is "unknown" to
`ScreenClassifier`, so `Scribe` runs in full-UI mode (`SCRIBE_PROMPT_UI`)
and no `ConfirmedFacts` are produced. **This is an expected, non-fatal
state** — the pipeline runs correctly with zero calibration, just with
Scribe doing more work per turn than it eventually needs to.

After **three consecutive "unknown" classifications**,
`ScreenBootstrapper` fires automatically:

1. It takes that turn's Scribe output — already computed, since an
   unknown screen already runs Scribe in full-UI mode — and drafts a new
   `configs/<game_id>/layouts/<screen_name>.json`.
2. The screen's name comes from Scribe's own `screen_name_guess`,
   sanitized the same way `game_id` is.
3. Candidate OCR boxes come from Scribe's `screen_elements` for that
   turn, converted from Scribe's normalized box format to layout pixel
   coordinates.
4. **Each box is OCR'd immediately and self-validated** — no human
   review required — via a coarse heuristic (`looks_like_real_text()`:
   is a large enough fraction of the extracted text alphanumeric). A box
   that passes is trusted for OCR going forward; one that doesn't is kept
   in the layout file but marked untrusted, so it doesn't get read from,
   which is safer than silently misreading garbage into `ConfirmedFacts`.

From this point on, that screen is classified via whole-frame SSIM against
the frame that triggered the bootstrap (a coarser match than a calibrated
anchor — see §4). No further action is needed for the pipeline to keep
working; calibration below is entirely optional cleanup.

## 3. Optional: manual calibration with `tools/inspect_coords.py`

Manual calibration exists to improve accuracy and add screen-identifying
anchors — it is never required for the pipeline to make forward progress.

```bash
python tools/inspect_coords.py "My Game Window Title" configs/my_new_game/layouts/combat.json
```

(First argument defaults to `"Slay the Spire"`, second defaults to
`layout.json` in the current directory — always pass both explicitly for
a real game, pointing at the specific screen's layout file under
`configs/<game_id>/layouts/`.)

This opens a live capture window ("Neow's Eye") over the current frame.
Controls:

| Action | Effect |
| --- | --- |
| Left-click + drag on empty space | Draw a new box; you'll be prompted for a name and shown a live OCR preview of the crop |
| Left-click an existing box | Select it (shows resize handles) |
| Drag a selected box's body | Reposition it |
| Drag a selected box's handle | Resize it |
| Right-click | Cancel the current drag, or deselect |
| Backspace / Delete | Delete the selected box |
| `h` | Toggle `requires_hover` on the next new box |
| `m` | Toggle `ignore_motion` on the next new box (see below) |
| `a` | Toggle `is_anchor` on the next new box (see below) |
| `s` | Seed draft boxes from a fresh Scribe call against the current frame (same mechanism as `ScreenBootstrapper`, run on demand) |
| `r` | Re-grab the current frame |
| `q` | Quit — every change is already saved to disk as you go |

A box you draw and name by hand is trusted immediately (no `scribe_auto`
tag, no self-confirmation needed — see `brain/perception/layout.py`'s `is_trusted`
property). Editing an existing `scribe_auto` draft's position/size also
promotes it to human-confirmed.

### Anchors (`a` toggle)

An anchor is a small, visually distinctive region used purely to identify
*which screen this is* — never OCR'd for its text content. Toggle `a`
before drawing a box over something that looks meaningfully different
between screens (an icon, a distinctive HUD corner) and a reference crop
of it gets saved into the layout file. `ScreenClassifier` then compares
this region via SSIM against the live frame each turn — this is a more
precise match than the whole-frame draft matching a bootstrapped screen
uses before any anchor exists, and is worth adding for two screens that
keep getting misclassified as each other.

### `ignore_motion` (`m` toggle)

Flag a region as `ignore_motion` if it animates independently of game
state — a background particle effect, an animated title-screen backdrop.
This gets unioned across every layout and masked out of `ChangeDetector`'s
frame diff entirely, rather than needing a global sensitivity threshold
tuned around it.

## 4. Screen-aware layouts

Calibration is per-*screen*, not per-game — `configs/<game_id>/layouts/`
holds one `<screen_name>.json` per named screen (`combat.json`,
`map.json`, `shop.json`, ...), since HUD element positions genuinely
differ between screens in most games. `screen_name` is either what
`ScreenBootstrapper` drafted automatically (§2) or whatever name you gave
a box when calibrating by hand — there's no separate registration step,
the filename stem *is* the screen name.

Once a screen has at least one trusted (non-anchor) calibrated element,
Scribe switches from `SCRIBE_PROMPT_UI` to the leaner
`SCRIBE_PROMPT_NO_UI` for that screen — OCR already owns the HUD values,
so Scribe only needs to extract scene entities, not transcribe every
label on screen.

## 5. When you need a plugin instead

If the game exposes its own structured state — a log file, a modding API,
anything that hands back exact facts instead of pixels to interpret — the
config-first path above isn't the right fit. `build_collector`'s
`collector_type` field is the dispatch seam for this (`"screen_ocr"` is
the only implemented value today). The worked example is
[`plugins/mtga/`](../plugins/mtga/README.md) — see
[`plugins/mtga/integration_notes.md`](../plugins/mtga/integration_notes.md)
for the full data-source evaluation if you're building a comparable
integration. A plugin only ever supplies data through the same
`Collector`/`RawObservation` contract every other Collector uses (see
`ARCHITECTURE.md` §4) — it gets no special access to Ally's reasoning.

## 6. Troubleshooting

- **The window stops being recognized after an update.** `ScreenCollector`
  matches on the *exact* window title string (`win32gui.FindWindow`). A
  game whose title includes a version number that changes between updates
  will need `configs/<game_id>/config.json`'s `window_title` updated (or
  the whole config regenerated) — this is a known limitation, not
  currently auto-handled. See `cabinet/configs/init_config.py`'s module docstring.
- **A screen never gets recognized / keeps re-bootstrapping.** Check
  `unknown_streak_threshold` (default 3, in `configs/user_config.json`)
  hasn't been set too high, and that the screen isn't visually similar
  enough to another already-drafted screen to be conflated — see
  `brain/perception/screen_classifier.py`'s module docstring on `draft_match_threshold`
  for this specific failure mode, and consider adding a calibrated anchor
  (§3) to disambiguate.
- **Missing/empty `layouts/` directory.** Non-fatal, logged, expected
  during early integration of any new game — the pipeline runs with empty
  `ConfirmedFacts` until at least one screen is calibrated or bootstrapped.
- **Screen capture doesn't work at all.** Screen-capture play is
  Windows-only today (`pywin32`/`win32gui`). This doesn't affect a
  structured-log Collector like MTGA's, which has no such dependency.