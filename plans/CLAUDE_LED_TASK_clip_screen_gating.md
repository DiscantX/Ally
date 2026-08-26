# CLAUDE_LED_TASK: CLIP-Based Screen Gating + Window Focus/Geometry Fixes

**Author:** Claude (architecture/planning) — for implementation by ZooCode (Gemini Flash Lite, Architect mode)
**Status:** Ready for implementation
**Depends on:** Nothing outside the current codebase. Adds one new dependency (`fastembed`).

---

## 0. Instructions for ZooCode

This task touches 7 files across collection, storage, and orchestration layers, plus adds 2 new
modules and a seed data file. **Please use Architect mode to subdivide this into the 5 phases
listed in §1 below, implementing them in order** — each phase depends on the one before it, and
each is independently testable before you move to the next. Do not skip ahead to Phase 4/5 wiring
before Phases 1–3 are complete and passing their own tests.

Every design decision below (thresholds aside, which are explicitly flagged as starting guesses)
has already been made. Where you have latitude — exact error message text, exact variable names
inside a function body, whether to extract a small private helper — use your judgment and match
the existing code style in the file you're editing. Where you do **not** have latitude — schema
shape, which file owns which responsibility, the skip-decision logic, the dedup logic — follow the
spec exactly. If something in this doc conflicts with what you observe in the actual current file
contents, the actual file wins for anything mechanical (e.g. an import path that's changed) — but
flag the conflict in your summary rather than silently reinterpreting a design decision.

This project's core, non-negotiable principle (see `docs/ally_decision_log.md` and `CLAUDE.md`):
**no pipeline step may require a human to notice, open a tool, and approve something before the
pipeline proceeds.** Manual tools remain fine for optional cleanup. Keep that in mind if you hit
a design choice this doc doesn't cover explicitly.

There is a **"Notes for Claude's code review"** section at the very end of this document.
**Ignore that section entirely — it is not part of your task.**

---

## 1. Summary of what's being built, and phase breakdown

Ally currently has exactly one mechanism that can skip a Scribe/Ally call
(`GenericHudCollector`'s `skip_ally` flag), and it only fires when a screen has calibrated OCR
*and* this turn's OCR values are byte-identical to last turn's. Any uncalibrated screen, or any
screen with no OCR fields at all (loading screens, static menus, cutscenes), currently gets a
fresh Scribe call on **every single settled frame**, forever. Separately, Ally has no way to
detect that the game window has lost focus (another app is now what's on screen) or that the
window's position on screen changed after startup (capture keeps reading stale coordinates).

This task adds:

1. **A window-focus check + a live geometry refresh**, fixing both the "Ally narrates whatever
   app I tabbed to" problem and a real standing bug where moving the game window to another
   monitor mid-session causes capture to keep reading the *old* screen coordinates forever.
2. **A local, zero-shot CLIP classifier** (ONNX, CPU, via `fastembed` — no GPU, no new heavy
   dependency like `torch`) that recognizes a small, explicit set of "not the game" screen types
   (a browser, a desktop, a chat app) purely from the pixels, as a backstop for the case where the
   game *is* focused but something is visually covering it (an overlay, a notification).
3. **A learned-category store** (SQLite + in-memory numpy, no vector database — see §6 for why)
   that grows automatically over time by reusing text Scribe already produces for free
   (`screen_name_guess`), with deduplication so near-identical phrasings don't pile up.

### Phase breakdown

| Phase | Files touched | Depends on |
|---|---|---|
| 1. Window focus + geometry refresh | `collectors/window_manager.py`, `collectors/configured_collector.py` | none |
| 2. CLIP infrastructure | `requirements.txt`, `configs/config_manager.py`, new `vision/clip_classifier.py` | none |
| 3. Category store | `memory/db.py`, new `vision/screen_category_store.py`, new `configs/clip_seed_categories.json` | Phase 2 |
| 4. Wiring into the live pipeline | `collectors/base.py`, `collectors/configured_collector.py`, `ally/core.py` | Phases 1–3 |
| 5. Tests | `tests/` (new files) | Phases 1–4 |

Phases 1 and 2 have no dependency on each other and can be done in either order or in parallel if
your tooling supports that; everything else is strictly sequential.

---

## 2. Phase 1 — Window focus check + geometry refresh bug fix

### 2.1 The bug, precisely

`collectors/window_manager.py`'s `ClientRect._set_rect_properties()` — which computes
`self.left`, `self.top`, `self.width`, `self.height` from the live window handle — is only ever
called twice: once from `__init__`, once from `move_to_top_left()` (itself called once, from
`prepare_window()`, at startup). `ScreenCollector.capture_bgr()` then reuses those same stored
coordinates on every subsequent call for the rest of the run. If the player drags the game window
to a different monitor (or resizes it) after startup, `mss.grab()` keeps reading the *old*
coordinates — capturing whatever now occupies that screen region, which could be a different
window, empty desktop, or content from a different monitor entirely. This is a real, currently-
unfixed bug, not new behavior being introduced by this task — we're fixing it here because the new
per-turn focus check needs to call into `win32gui` anyway, so refreshing geometry in the same place
is nearly free.

### 2.2 `collectors/window_manager.py` changes

Add two new public methods to `ClientRect`. Do not change the existing constructor or
`_set_rect_properties` logic — just expose it and add a focus check:

```python
def refresh(self) -> bool:
    """Re-resolve this window's client-area geometry from its live handle.
    Call this every turn (it's a couple of cheap win32 calls) so a window
    that's been dragged to another monitor or resized after startup gets
    picked up -- capture_bgr() otherwise keeps reading whatever pixel
    region it was first calibrated to, forever, silently.

    Returns False (without raising) if the handle is no longer valid --
    e.g. the game was closed -- so callers can treat "window is gone" the
    same way they already treat "window was never found."
    """
    if not self.handle or not win32gui.IsWindow(self.handle):
        return False
    try:
        self._set_rect_properties()
        return True
    except Exception:
        return False

def is_foreground(self) -> bool:
    """True if this window is currently the OS-level focused window.
    Cheap (one win32 call, no frame capture) -- meant to be checked
    before doing any capture work at all, not just before commenting on
    a captured frame."""
    if not self.handle:
        return False
    return win32gui.GetForegroundWindow() == self.handle
```

No other changes to this file. `move_to_top_left()` and `bring_to_foreground()` stay as-is.

### 2.3 `collectors/configured_collector.py` changes — `GenericHudCollector.capture()`

At the very top of `capture()`, before the existing `frame_bgr = self.screen.capture_bgr()` line,
add:

```python
def capture(self) -> RawObservation:
    # Refresh live geometry every turn (fixes stale-coordinates-after-
    # window-move) and check focus BEFORE doing any capture work at all --
    # no point grabbing and processing a frame from a window that isn't
    # even focused.
    self.screen.rect.refresh()
    if not self.screen.rect.is_foreground():
        return RawObservation(image=None, changed=False, skip_scribe_reason="not_foreground")

    frame_bgr = self.screen.capture_bgr()
    # ... existing code continues unchanged from here
```

This means: not-foreground turns never reach the CLIP classifier, never reach `ChangeDetector`,
never capture a frame at all. `AllyCore.run_turn()` already returns early (logs "No image
captured") whenever `observation.image is None` — that existing behavior is exactly what we want
here, so no change is needed in `ally/core.py` for this specific case. (`skip_scribe_reason` is a
new field added in Phase 4 — implement Phase 1 first with a plain `RawObservation(image=None,
changed=False)` if you're doing Phase 1 before Phase 4's dataclass change lands, and revisit this
one line once `RawObservation` has the new field.)

**Do not** add any occlusion/covering-window detection in this phase — that's what the Phase 4
CLIP `off_game` gate is for, and it's a genuinely different failure mode (window IS focused but
something is drawn on top of it) that a foreground check cannot catch.

---

## 3. Phase 2 — CLIP infrastructure

### 3.1 Dependency: `fastembed`, not `torch`/`open_clip`

`requirements.txt` already doesn't include any deep-learning framework, and this project's stated
preference (see `docs/ally_decision_log.md`, "Embeddings / vector search" section) is local, ONNX,
CPU-quantized models over heavier alternatives — `fastembed` was already named there as "the
concrete candidate." `fastembed` (the library behind Qdrant's local-mode embeddings) ships
ONNX-quantized CLIP models with a paired image/text API and needs no `torch` install. Add to
`requirements.txt`:

```
fastembed
numpy
```

(`numpy` is very likely already present transitively via `opencv-python`/`scikit-image`, but this
task's new code imports it directly, so make it an explicit top-level dependency rather than
relying on a transitive one.)

**Verify the exact model identifiers before finalizing the config default.** At the time this doc
was written, `fastembed`'s CLIP support used model names along the lines of
`"Qdrant/clip-ViT-B-32-vision"` (image tower) and `"Qdrant/clip-ViT-B-32-text"` (text tower) — a
matched pair in the same embedding space. **Confirm the currently-correct names** by running (in
your dev environment, after `pip install fastembed`):

```python
from fastembed import ImageEmbedding, TextEmbedding
print([m["model"] for m in ImageEmbedding.list_supported_models() if "clip" in m["model"].lower()])
print([m["model"] for m in TextEmbedding.list_supported_models() if "clip" in m["model"].lower()])
```

Use whatever the actual current CLIP ViT-B/32 (or closest available small/quantized CLIP) model
names are for the two new config keys in §3.2. If ViT-B/32 specifically isn't available, prefer
the smallest available CLIP variant — the whole point of this design is staying light on an 8GB
CPU-only machine.

### 3.2 New config keys — `configs/config_manager.py`

This file isn't included in the source you were given, but every other subsystem in this codebase
(`ChangeDetector`, `ScreenClassifier`, `NarrativeMemoryManager`, etc.) reads its tunables via
`load_user_config()["some_key"]`, with defaults presumably defined in this file's default-config
dict. **Open `configs/config_manager.py`, find where existing defaults like `threshold_percent`,
`match_threshold`, `draft_match_threshold`, `unknown_streak_threshold` are defined, and add the
following new keys in the same place, following the exact same pattern** (default dict entry +
whatever getter/validation logic the existing keys go through):

```python
"clip_enabled": True,
"clip_image_model": "Qdrant/clip-ViT-B-32-vision",   # verify against §3.1 before finalizing
"clip_text_model": "Qdrant/clip-ViT-B-32-text",      # verify against §3.1 before finalizing
"clip_skip_confidence_threshold": 0.5,   # softmax probability of the top match; see §5.2
"clip_skip_margin_threshold": 0.15,      # required gap between top-1 and top-2 probability; see §5.2
"clip_category_dedup_threshold": 0.75,   # difflib text-similarity cutoff; same scale/convention as EntityRegistry.match_threshold
```

**All three CLIP threshold values are explicitly starting guesses, not measured values** — same
caveat this codebase already applies to its SSIM thresholds (see `vision/screen_classifier.py`'s
module docstring: "This is still a coarse, un-tuned guess, not a measured value"). Do not treat
these as final; they should be exposed the same way SSIM thresholds are (readable via
`load_user_config()`, so they can eventually be surfaced in `gui/settings_window.py` — **do not**
add them to the settings GUI in this task, that's out of scope, just make sure they're readable
from config the same way every other tunable in this codebase is).

### 3.3 New file: `vision/clip_classifier.py`

```python
"""Local, zero-shot CLIP classifier (ONNX via fastembed, CPU-only, no
torch dependency). Used as a semantic pre-filter ahead of Scribe --
never as a replacement for vision/screen_classifier.py's SSIM-based
matching, which does a structurally different job (exact same-screen
identity for OCR layout routing, not general screen-type recognition).
See ally_decision_log.md for the SSIM-vs-CLIP distinction if this
comment needs more context later.

CLIP's image and text encoders are frozen, pretrained models -- nothing
here trains or fine-tunes anything. "Learning" a new category (see
vision/screen_category_store.py) only ever means "embed a new sentence
once and cache the vector," never updating the model itself.
"""

import numpy as np
from PIL import Image

from configs.config_manager import load_user_config
from logger import log

try:
    from fastembed import ImageEmbedding, TextEmbedding
    _FASTEMBED_AVAILABLE = True
except ImportError:
    _FASTEMBED_AVAILABLE = False


class ClipClassifier:
    """Thin wrapper pairing fastembed's CLIP image and text towers.
    Construct once (model loading has real cost) and share the instance
    -- see ally/core.py for where this gets constructed and injected."""

    def __init__(self, image_model: str | None = None, text_model: str | None = None):
        config = load_user_config()
        self.enabled = config.get("clip_enabled", True) and _FASTEMBED_AVAILABLE
        if not _FASTEMBED_AVAILABLE:
            log(
                "[ClipClassifier] fastembed not installed -- CLIP screen gating "
                "disabled, pipeline behaves as if this feature doesn't exist. "
                "`pip install fastembed` to enable it."
            )
            return
        if not self.enabled:
            return

        image_model_name = image_model or config["clip_image_model"]
        text_model_name = text_model or config["clip_text_model"]
        try:
            self._image_model = ImageEmbedding(image_model_name)
            self._text_model = TextEmbedding(text_model_name)
        except Exception as e:
            log("[ClipClassifier] Failed to load CLIP models ({e}) -- disabling CLIP gating.", e=e)
            self.enabled = False

    def encode_image(self, frame_bgr: np.ndarray) -> np.ndarray | None:
        """BGR numpy frame (as produced by ScreenCollector.capture_bgr())
        -> a single L2-normalized embedding vector, or None if disabled/
        failed. Converts to RGB PIL internally since that's the safe,
        version-stable input shape for fastembed."""
        if not self.enabled:
            return None
        import cv2
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        try:
            embedding = next(self._image_model.embed([pil_image]))
            return self._normalize(np.asarray(embedding))
        except Exception as e:
            log("[ClipClassifier] Image encode failed: {e}", e=e)
            return None

    def encode_text(self, text: str) -> np.ndarray | None:
        """Single sentence -> a single L2-normalized embedding vector, in
        the same space as encode_image's output."""
        if not self.enabled:
            return None
        try:
            embedding = next(self._text_model.embed([text]))
            return self._normalize(np.asarray(embedding))
        except Exception as e:
            log("[ClipClassifier] Text encode failed: {e}", e=e)
            return None

    @staticmethod
    def _normalize(vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
```

Follow the same "unavailable dependency degrades gracefully, logged once, pipeline behaves as if
the feature doesn't exist" pattern `vision/change_detector.py` already uses for
`_SSIM_AVAILABLE`. **Do not raise on missing fastembed** — the rest of the pipeline must work
exactly as it does today if this dependency isn't installed.

---

## 4. Phase 3 — Category store

### 4.1 Schema — add to `memory/db.py`

Add this table creation to `MemoryDB._init_db()`, in the same `try` block as the other
`CREATE TABLE IF NOT EXISTS` statements, following the exact same style (same connection object,
committed together with everything else in that method):

```python
conn.execute("""
    CREATE TABLE IF NOT EXISTS screen_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id TEXT,
        kind TEXT NOT NULL,
        text TEXT NOT NULL,
        embedding BLOB NOT NULL,
        source TEXT NOT NULL DEFAULT 'learned',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
```

Notes on the schema:
- `game_id` is **nullable** — `NULL` means globally shared (used for `off_game` seed rows and all
  `normal`-kind learned rows). A non-null value scopes a row to one game (reserved for `low_value`
  rows — **not populated by this task**, see §4.4).
- `kind` is one of `"off_game"`, `"normal"`, `"low_value"` (plain TEXT, not an enum — same
  convention `entities.entity_type` and `narrative_turns.tier` already use in this file).
- `embedding` is a serialized `float32` numpy array. Use `arr.astype(np.float32).tobytes()` to
  write, `np.frombuffer(blob, dtype=np.float32)` to read.
- `source` is `"seed"` (hand-authored, loaded once at first run) or `"learned"` (appended
  automatically from Scribe's output at runtime).

Add two new methods to `MemoryDB`, matching the existing method style in this file (own
connection per call, `finally: conn.close()`):

```python
def get_screen_categories(self, game_id: str) -> list[dict[str, Any]]:
    """Rows visible to this game: everything with game_id IS NULL (global
    off_game seeds + all learned normal-kind rows), plus this game's own
    game_id-scoped rows (reserved for low_value, currently always empty
    -- see screen_category_store.py)."""
    conn = self._connect()
    try:
        cursor = conn.execute(
            "SELECT * FROM screen_categories WHERE game_id IS NULL OR game_id = ?",
            (game_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def insert_screen_category(
    self, game_id: str | None, kind: str, text: str, embedding: bytes, source: str = "learned"
) -> None:
    conn = self._connect()
    try:
        conn.execute(
            "INSERT INTO screen_categories (game_id, kind, text, embedding, source) VALUES (?, ?, ?, ?, ?)",
            (game_id, kind, text, embedding, source)
        )
        conn.commit()
    finally:
        conn.close()

def count_screen_categories(self, source: str | None = None) -> int:
    """Used at startup to decide whether the seed set still needs loading."""
    conn = self._connect()
    try:
        if source:
            cursor = conn.execute("SELECT COUNT(*) as c FROM screen_categories WHERE source = ?", (source,))
        else:
            cursor = conn.execute("SELECT COUNT(*) as c FROM screen_categories")
        row = cursor.fetchone()
        return row["c"] if row else 0
    finally:
        conn.close()
```

### 4.2 Seed data — new file `configs/clip_seed_categories.json`

Plain JSON, hand-authored, loaded once (idempotently — check `count_screen_categories(source="seed")
== 0` before inserting, so re-running Ally doesn't re-seed every startup):

```json
[
    {"text": "a web browser window showing a webpage"},
    {"text": "a video streaming website playing a video"},
    {"text": "a desktop file explorer window"},
    {"text": "a chat or messaging application"},
    {"text": "a code editor or IDE with source code"},
    {"text": "an email inbox application"},
    {"text": "a video call or conferencing application"},
    {"text": "a music streaming application"},
    {"text": "an operating system desktop with icons"},
    {"text": "a spreadsheet application"},
    {"text": "a document editor showing text"},
    {"text": "a social media feed"}
]
```

All rows in this file get inserted with `kind="off_game"`, `game_id=None`, `source="seed"`. Feel
free to add a few more entries in this same spirit if you think of obvious gaps (a terminal
window, a PDF viewer) — the exact list isn't sacred, the *category* (things that are clearly not
gameplay) is what matters.

### 4.3 New file: `vision/screen_category_store.py`

```python
"""Learned screen-category store: SQLite for persistence (via MemoryDB,
same pattern as entities/personality_journal), plain numpy for the
actual similarity math. Deliberately NOT a vector database -- see
ally_decision_log.md for the sizing rationale (a few hundred short
text-category embeddings is well below the scale where an ANN index
like Qdrant/LanceDB pays for itself over brute-force cosine similarity;
brute force is also exact rather than approximate at this size).

Three category kinds, two very different roles:
- "off_game": hand-seeded, global (game_id=None), drives the skip
  decision. See configs/clip_seed_categories.json.
- "normal": auto-learned from Scribe's screen_name_guess whenever
  Scribe runs on a screen CLIP didn't already confidently recognize.
  Global (game_id=None) -- cross-game reuse here is a feature (a
  "combat screen" label from one game doesn't need re-learning for a
  visually-similar one), and the failure mode of an unnecessary dedup
  miss is trivial. NEVER drives a skip on its own.
- "low_value": reserved for game-scoped "boring, don't bother
  commenting" screens (loading screens, idle title cards). Schema and
  query filtering both support this kind, but nothing in this pass
  populates it -- auto-promoting a "normal" category to "low_value"
  needs a repetition/staleness signal this pass doesn't have, and
  guessing at one risks silently gating real gameplay (see the doc
  this was scoped from for the full reasoning). Explicitly deferred,
  not forgotten.
"""

import difflib
import json
import os
import threading
from dataclasses import dataclass

import numpy as np

from configs.config_manager import load_user_config
from memory.db import MemoryDB
from vision.clip_classifier import ClipClassifier
from logger import log

SEED_FILE = "configs/clip_seed_categories.json"


@dataclass
class CategoryMatch:
    kind: str
    text: str
    top_probability: float
    margin: float
    confident: bool


class ScreenCategoryStore:
    def __init__(self, db: MemoryDB, clip: ClipClassifier):
        self.db = db
        self.clip = clip
        self._lock = threading.Lock()  # same coarse-lock convention as EntityRegistry
        config = load_user_config()
        self.skip_confidence_threshold = config["clip_skip_confidence_threshold"]
        self.skip_margin_threshold = config["clip_skip_margin_threshold"]
        self.dedup_threshold = config["clip_category_dedup_threshold"]

        self._ensure_seeded()
        # Global pool (game_id IS NULL): off_game + normal rows, shared
        # across every game. Loaded once; grown in-memory + in the DB as
        # maybe_learn() runs. Per-game low_value rows are loaded
        # per-game via for_game() below, since they don't apply globally.
        self._rows: list[dict] = []  # each: {id, game_id, kind, text, embedding: np.ndarray}
        self._matrix: np.ndarray | None = None  # (N, D) stacked embeddings, kept in sync with _rows
        self._load_global()

    def _ensure_seeded(self) -> None:
        if self.db.count_screen_categories(source="seed") > 0:
            return
        if not os.path.exists(SEED_FILE):
            log("[ScreenCategoryStore] No seed file at {path} -- starting with zero off_game categories.", path=SEED_FILE)
            return
        if not self.clip.enabled:
            log("[ScreenCategoryStore] CLIP unavailable -- cannot embed seed categories, skipping seed load.")
            return
        with open(SEED_FILE, "r") as f:
            seeds = json.load(f)
        for entry in seeds:
            embedding = self.clip.encode_text(entry["text"])
            if embedding is None:
                continue
            self.db.insert_screen_category(
                game_id=None, kind="off_game", text=entry["text"],
                embedding=embedding.astype(np.float32).tobytes(), source="seed",
            )
        log("[ScreenCategoryStore] Seeded {n} off_game categories.", n=len(seeds))

    def _load_global(self) -> None:
        """Load every game_id IS NULL row (off_game seeds + all normal
        rows, across every game) into the in-memory matrix. low_value
        rows are per-game and NOT loaded here -- see for_game()."""
        with self._lock:
            rows = self.db.get_screen_categories(game_id="__never_matches__")
            # get_screen_categories already includes game_id IS NULL rows
            # for ANY game_id argument, per its query -- see §4.1. Calling
            # with a sentinel that can't match a real game_id is fine here
            # since we only want the global (NULL) subset at store-init
            # time, before any specific game is known.
            self._rows = [self._row_to_dict(r) for r in rows if r["game_id"] is None]
            self._rebuild_matrix()

    def _row_to_dict(self, row: dict) -> dict:
        return {
            "id": row["id"], "game_id": row["game_id"], "kind": row["kind"],
            "text": row["text"],
            "embedding": np.frombuffer(row["embedding"], dtype=np.float32),
        }

    def _rebuild_matrix(self) -> None:
        if not self._rows:
            self._matrix = None
            return
        self._matrix = np.stack([r["embedding"] for r in self._rows])

    def for_game(self, game_id: str) -> "GameScopedView":
        """Returns a view that also includes this game's own low_value
        rows on top of the global pool. Loads that game's low_value rows
        from the DB once and caches them for the life of this store."""
        with self._lock:
            game_rows = [
                self._row_to_dict(r) for r in self.db.get_screen_categories(game_id=game_id)
                if r["game_id"] == game_id and r["kind"] == "low_value"
            ]
        return GameScopedView(store=self, game_id=game_id, game_rows=game_rows)

    def query(self, image_embedding: np.ndarray, rows: list[dict], matrix: np.ndarray | None) -> CategoryMatch | None:
        """Cosine similarity -> CLIP-style temperature-scaled softmax
        (logit_scale ~100, matching CLIP's own training setup) -> top
        match, its probability, and its margin over the second-best.
        Returns None if there's nothing in scope to compare against."""
        if matrix is None or not rows:
            return None
        similarities = matrix @ image_embedding  # both L2-normalized -> this is cosine similarity
        scaled = similarities * 100.0
        exp = np.exp(scaled - np.max(scaled))  # numerically stable softmax
        probs = exp / exp.sum()
        top_idx = int(np.argmax(probs))
        top_prob = float(probs[top_idx])
        if len(probs) > 1:
            second_prob = float(np.partition(probs, -2)[-2])
        else:
            second_prob = 0.0
        margin = top_prob - second_prob
        confident = top_prob >= self.skip_confidence_threshold and margin >= self.skip_margin_threshold
        return CategoryMatch(
            kind=rows[top_idx]["kind"], text=rows[top_idx]["text"],
            top_probability=top_prob, margin=margin, confident=confident,
        )

    def maybe_learn(self, text: str, game_id: str) -> None:
        """Called after Scribe actually runs. Dedups against the FULL
        global pool (off_game + normal, all games) via difflib text
        matching -- same style as EntityRegistry's fuzzy resolution --
        before embedding and inserting. Always inserts as kind="normal",
        game_id=None (see module docstring for why normal rows stay
        global). No-ops if CLIP is unavailable."""
        if not self.clip.enabled or not text.strip():
            return
        with self._lock:
            existing_texts = [r["text"] for r in self._rows]
        matches = difflib.get_close_matches(
            text.strip().lower(), [t.lower() for t in existing_texts],
            n=1, cutoff=self.dedup_threshold,
        )
        if matches:
            return  # near-duplicate of something we already have -- skip
        embedding = self.clip.encode_text(text.strip())
        if embedding is None:
            return
        self.db.insert_screen_category(
            game_id=None, kind="normal", text=text.strip(),
            embedding=embedding.astype(np.float32).tobytes(), source="learned",
        )
        with self._lock:
            self._rows.append({"id": None, "game_id": None, "kind": "normal", "text": text.strip(), "embedding": embedding})
            self._rebuild_matrix()


@dataclass
class GameScopedView:
    """Read-only per-game view: global pool + this game's own low_value
    rows. `store.query()` is called against this view's combined
    rows/matrix, never against the store's raw global-only state, so
    game-scoped low_value rows can never leak into another game's skip
    decision (see the design doc's category-collision discussion)."""
    store: ScreenCategoryStore
    game_id: str
    game_rows: list[dict]

    def classify(self, image_embedding: np.ndarray) -> CategoryMatch | None:
        with self.store._lock:
            combined_rows = self.store._rows + self.game_rows
        if not combined_rows:
            return None
        matrix = np.stack([r["embedding"] for r in combined_rows])
        return self.store.query(image_embedding, combined_rows, matrix)
```

A few implementation notes for whoever writes this:
- The `get_screen_categories(game_id="__never_matches__")` call in `_load_global()` is a slightly
  awkward way to say "give me only the global rows" reusing the one query method already defined
  in `memory/db.py`. If you'd rather add a dedicated `get_global_screen_categories()` method to
  `MemoryDB` instead of this sentinel trick, that's a fine, arguably cleaner alternative — your
  call, just keep the semantics (global rows only) identical.
- `GameScopedView.classify()` is what `configured_collector.py` actually calls each turn (see
  Phase 4) — never call `ScreenCategoryStore.query()` directly from outside this file.

### 4.4 Explicitly deferred: auto-promotion to `low_value`

Do **not** attempt to build a heuristic in this task that automatically promotes a `normal`
category to `low_value` (e.g. "if this category matches N turns in a row, treat it as boring").
This was considered during design and deliberately deferred — a repetition-based heuristic risks
silently gating real, meaningful gameplay that happens to look visually similar turn-to-turn (a
slow-paced strategy screen, for instance), and building one without real playtesting data to tune
it against is more likely to introduce a "Ally went quiet and nobody knows why" bug than to save
API calls. The schema and query path both already support `low_value` correctly (game-scoped, per
§4.1/§4.3) so a future task can add the promotion mechanism without touching this one's code. In
this pass, `low_value` will simply always be empty per game, and that's expected and correct.

---

## 5. Phase 4 — Wiring into the live pipeline

### 5.1 `collectors/base.py` — `RawObservation` new fields

Add two new fields to the existing `RawObservation` dataclass, both with safe defaults so nothing
that constructs a `RawObservation` elsewhere in the codebase needs to change:

```python
screen_category: str | None = None
"""Best-matched CLIP category text for this frame, if any confident
match was found (regardless of whether it caused a skip). None if CLIP
is disabled/unavailable or nothing matched confidently."""

skip_scribe_reason: str = "none"
"""One of 'none', 'not_foreground', 'off_game', 'low_value'. Distinct
from the existing skip_ally flag (which is the OCR-facts-unchanged
guard) -- this is the new CLIP/focus-driven guard. See ally/core.py's
run_turn() for how the two combine."""
```

### 5.2 `collectors/configured_collector.py` — full updated `capture()` flow

Update `GenericHudCollector.__init__` to accept the shared store/classifier (constructed once by
`AllyCore`, see §5.4 — **do not** have `GenericHudCollector` construct its own `ClipClassifier`
instance, since model loading is expensive and the same instance needs to be shared with the
post-Scribe learning step in `ally/core.py`):

```python
def __init__(
    self,
    config: CollectorConfig,
    clip_classifier: "ClipClassifier | None" = None,
    category_store: "ScreenCategoryStore | None" = None,
):
    self.config = config
    self.screen = ScreenCollector(config.window_title)
    self.readers, self.classifier = build_screen_layouts(config.layout_dir, config.source_tag)
    self.bootstrapper = ScreenBootstrapper(config.layout_dir, unknown_streak_threshold=3)
    self._last_frame_bgr = None
    self._last_confirmed_facts: list[ConfirmedFact] = []
    self.clip_classifier = clip_classifier
    self.category_store = category_store
    # ... existing ignore_regions block unchanged
```

Full updated `capture()` (showing the complete method so the insertion points are unambiguous —
everything after the focus check and before the final `return obs` that isn't new is unchanged
from the current implementation):

```python
def capture(self) -> RawObservation:
    self.screen.rect.refresh()
    if not self.screen.rect.is_foreground():
        return RawObservation(image=None, changed=False, skip_scribe_reason="not_foreground")

    frame_bgr = self.screen.capture_bgr()
    if frame_bgr is None:
        return RawObservation(image=None, changed=False)

    self._last_frame_bgr = frame_bgr
    changed = self.screen.change_detector.has_changed(frame_bgr)

    screen_category: str | None = None
    skip_scribe_reason = "none"

    # CLIP semantic gate -- only worth running on frames that actually
    # changed (no point re-classifying a frame ChangeDetector already
    # said is unchanged from last turn).
    if changed and self.clip_classifier is not None and self.category_store is not None and self.clip_classifier.enabled:
        image_embedding = self.clip_classifier.encode_image(frame_bgr)
        if image_embedding is not None:
            view = self.category_store.for_game(self.config.game_id)
            match = view.classify(image_embedding)
            if match is not None:
                screen_category = match.text
                if match.confident and match.kind in ("off_game", "low_value"):
                    skip_scribe_reason = match.kind

    match_result = self.classifier.classify(frame_bgr)
    bootstrap_ready = self.bootstrapper.note_classification(match_result.screen_name)
    reader = self.readers.get(match_result.screen_name)
    confirmed_facts = reader.read(frame_bgr) if reader else []

    skip_ally = False
    if (self._last_confirmed_facts and confirmed_facts and
            len(self._last_confirmed_facts) == len(confirmed_facts)):
        facts_match = True
        for last_fact, curr_fact in zip(self._last_confirmed_facts, confirmed_facts):
            if last_fact.key != curr_fact.key or last_fact.value != curr_fact.value:
                facts_match = False
                break
        if facts_match:
            skip_ally = True

    self._last_confirmed_facts = confirmed_facts.copy()

    image = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    obs = RawObservation(
        image=image, confirmed_facts=confirmed_facts, changed=changed,
        screen_name=match_result.screen_name, screen_confidence=match_result.confidence,
        bootstrap_ready=bootstrap_ready,
        screen_category=screen_category,
        skip_scribe_reason=skip_scribe_reason,
    )
    obs.skip_ally = skip_ally
    return obs
```

Note that `ScreenClassifier.classify()` (SSIM) still runs **unconditionally**, regardless of what
the CLIP gate decided — per the design discussion, SSIM's job (picking the OCR layout) is
independent of whether we end up skipping Scribe, and it's cheap enough that skipping it wouldn't
save anything meaningful.

Also update `build_collector()` at the bottom of this file to accept and forward the same two
optional params, so `AllyCore` can inject them:

```python
def build_collector(
    config_path: str,
    clip_classifier: "ClipClassifier | None" = None,
    category_store: "ScreenCategoryStore | None" = None,
) -> GenericHudCollector:
    config = load_collector_config(config_path)
    if config.collector_type != "screen_ocr":
        raise NotImplementedError(...)  # unchanged
    return GenericHudCollector(config, clip_classifier=clip_classifier, category_store=category_store)
```

Add the two new imports at the top of the file:
```python
from vision.clip_classifier import ClipClassifier
from vision.screen_category_store import ScreenCategoryStore
```
(These are only used for type hints in the signatures above — fine as regular imports, no need for
`TYPE_CHECKING` guards given every other file in this codebase imports plainly.)

### 5.3 `ally/core.py` — extending the skip decision + the learning step

**5.3.1 — Broaden the skip check.** In `run_turn()`, the existing line:

```python
skip_ally = getattr(observation, 'skip_ally', False)
```

becomes:

```python
skip_scribe_reason = getattr(observation, 'skip_scribe_reason', 'none')
skip_ally = getattr(observation, 'skip_ally', False) or skip_scribe_reason != 'none'
```

Everything below that in the existing `if not skip_ally: / else:` branches stays structurally the
same, but the `else` branch's log message and the `AllyOutput.analysis` stub text should
distinguish *why* the turn was skipped, since "confirmed facts unchanged" and "not focused" and
"recognized as off-game" are meaningfully different situations worth being able to tell apart in
the logs later. Replace the existing:

```python
log("--- Skipping Scribe/Ally (confirmed facts unchanged) ---")
ally_output = AllyOutput(
    analysis="(confirmed facts unchanged this turn -- no new commentary)",
    actions=[],
    run_boundary="none",
)
```

with:

```python
skip_messages = {
    "off_game": f"(CLIP recognized this as off-game content: '{observation.screen_category}' -- pausing commentary)",
    "low_value": f"(CLIP recognized this as a low-value screen: '{observation.screen_category}' -- skipping commentary)",
    "none": "(confirmed facts unchanged this turn -- no new commentary)",
}
reason_label = skip_scribe_reason if skip_scribe_reason != "none" else "facts_unchanged"
log("--- Skipping Scribe/Ally (reason={reason}) ---", reason=reason_label)
ally_output = AllyOutput(
    analysis=skip_messages.get(skip_scribe_reason, skip_messages["none"]),
    actions=[],
    run_boundary="none",
)
```

**Important:** when `skip_scribe_reason == "off_game"`, this skip stub still gets passed to
`self.memory_manager.record_turn(...)` in the existing code path below, exactly like every other
skip today. Per the design discussion, an off-game pause should **not** get woven into the run's
narrative memory as if it were something that happened in-game. Find the existing block:

```python
if self.memory_manager is not None:
    self.memory_manager.record_turn(
        self.sandbox.turn,
        ally_output.analysis if not skip_ally else "skip_ally: confirmed facts unchanged"
    )
```

and change the condition so `off_game` turns are excluded from `record_turn` entirely (everything
else — `low_value`, `not_foreground` via the earlier no-image early return, facts-unchanged — keeps
recording exactly as it does today):

```python
if self.memory_manager is not None and skip_scribe_reason != "off_game":
    self.memory_manager.record_turn(
        self.sandbox.turn,
        ally_output.analysis if not skip_ally else f"skip_ally: {reason_label}"
    )
```

**5.3.2 — The learning step.** Inside the existing `if not skip_ally:` branch (i.e. only on turns
where Scribe actually ran), immediately after this existing line:

```python
scribe_output = self.scribe.extract(observation.image, include_ui=include_ui)
```

add:

```python
if self.category_store is not None and self.collector is not None:
    self.category_store.maybe_learn(scribe_output.screen_name_guess, self.collector.config.game_id)
```

That's the entire learning mechanism — no new API call, reusing output Scribe already produces.
Dedup inside `maybe_learn` makes it safe to call this unconditionally every time Scribe runs,
including turns where CLIP already had a confident (but non-skipping, e.g. `normal`-kind) match.

**5.3.3 — Constructing and injecting the shared instances.** In `AllyCore.__init__`, alongside the
existing `self.provider = GeminiProvider()` / `self.scribe = Scribe(...)` block, add:

```python
from vision.clip_classifier import ClipClassifier
from vision.screen_category_store import ScreenCategoryStore

# ... inside __init__, near self.db = MemoryDB():
self.clip_classifier = ClipClassifier()
self.category_store = ScreenCategoryStore(db=self.db, clip=self.clip_classifier)
```

`self.db = MemoryDB()` must already exist above this point in `__init__` (it does, in the current
code) since `ScreenCategoryStore` needs it. Then in `initialize_run()`, wherever
`self.collector = build_collector(self.config_path)` is currently called, change it to:

```python
self.collector = build_collector(
    self.config_path,
    clip_classifier=self.clip_classifier,
    category_store=self.category_store,
)
```

This is the *only* place `build_collector` gets called with the live game config (the
`image_path` branch above it in `initialize_run()` never constructs a `collector` at all, so
nothing else needs to change there).

### 5.4 Config default for `game_id` used before a collector exists

`ScreenCategoryStore.__init__` calls `_load_global()`, which doesn't need a `game_id` at all (it's
explicitly the global-only load). `for_game()` is only ever called from inside
`GenericHudCollector.capture()`, by which point `self.config.game_id` is always a real value. No
special-casing needed here — just confirming there's no ordering problem, since `AllyCore`
constructs `ScreenCategoryStore` before `self.collector` exists.

---

## 6. Explicitly out of scope for this task

Do not build any of the following — each was discussed and deliberately not chosen, for the
reasons noted, and building them anyway would be scope creep against an explicit decision:

- **Any vector database (Qdrant, LanceDB, sqlite-vec, etc.).** At the scale of a few hundred short
  text-category embeddings, a flat numpy matrix loaded at startup and appended to at runtime is
  both faster and simpler than any ANN-indexed store — indexing overhead only pays for itself at
  roughly tens of thousands of vectors or more, which this table will not reach. If a future task
  needs a real vector index (e.g. for entity-resolution-at-scale, already flagged as deferred in
  `ally_decision_log.md`), that's a separate, much-larger-scale decision — nothing here should be
  built to anticipate it.
- **CLIP-based VQA / "ask CLIP questions about the scene."** Considered and rejected: base CLIP
  can't do free-form question answering, only closed-set caption matching, and it's specifically
  weak at exactly the things you'd want precise answers to (counting, exact numbers, fine spatial
  relationships) — the calibrated OCR pipeline already does that better. The narrow useful subset
  (closed-set binary/small-multiclass state flags) is just a restatement of the screen-category
  matching already built here, not a separate feature.
- **`GenreTracker` integration.** `GenreTracker`'s existing Scribe-driven accuracy is already
  good; there's no problem here for CLIP to solve. Do not wire `screen_category` into
  `GenreTracker` in this task.
- **Aesthetic/atmosphere flavor tagging.** Only would have mattered on turns where Scribe gets
  skipped — but a skipped turn means CLIP already decided there's nothing worth describing, so
  there's no case left where flavor text without substance would make sense.
- **Auto-promotion of `normal` categories to `low_value`.** See §4.4 — schema supports it, nothing
  populates it yet, and that's intentional.
- **Occlusion/covering-window detection beyond the CLIP `off_game` category itself.** No separate
  "is something drawn on top of the game" detector beyond what CLIP's zero-shot classification
  already gives you for free.
- **Surfacing the new CLIP threshold config keys in `gui/settings_window.py`.** They should be
  readable via `load_user_config()` the same way every other tunable is, but adding UI controls
  for them is a separate task.

---

## 7. Phase 5 — Tests

Follow this project's existing conventions exactly: `unittest.TestCase` subclasses (not bare
pytest functions), placed in `tests/`, run via `python -m unittest discover tests`. Remember:
**`MagicMock()` cannot be passed as a PIL image to OpenCV — use `Image.new("RGB", (w, h))`
instead**, for any test that needs to hand a fake frame through code that touches `cv2`.

Write the following new test files:

**`tests/test_screen_category_store.py`**
- Dedup: seed the store (or a temp `MemoryDB`) with one category, call `maybe_learn()` with a
  near-identical phrasing, assert no second row was inserted (check `count_screen_categories()`
  before/after, or inspect `store._rows` length).
- Dedup negative case: `maybe_learn()` with a genuinely different phrasing does insert a new row.
- `game_id` scoping: insert a `low_value` row for `game_id="game_a"`, verify `for_game("game_a")`
  includes it and `for_game("game_b")` does not, while a `normal`/`off_game` row (game_id=None)
  appears in both.
- Seed idempotency: construct `ScreenCategoryStore` twice against the same DB, assert the seed
  file's categories were only inserted once (`count_screen_categories(source="seed")` unchanged
  on the second construction).
- Mock `ClipClassifier` (or construct a real one with `clip_enabled=False` in config) so these
  tests don't require downloading real ONNX model weights in CI.

**`tests/test_window_manager_refresh.py`**
- Guard the whole module the same way MTGA's real-environment tests do (`skipTest` / a
  module-level skip decorator) if `pywin32`/`win32gui` isn't importable, since this is
  Windows-only exactly like the rest of `collectors/window_manager.py`.
- Mock `win32gui.GetForegroundWindow` and `win32gui.IsWindow` to verify `is_foreground()` returns
  the correct boolean for matching/non-matching handles, and that `refresh()` returns `False`
  (without raising) when `IsWindow` reports the handle is gone.

**`tests/test_clip_gate_integration.py`**
- Using `unittest.mock.MagicMock` for `ClipClassifier` and `ScreenCategoryStore` (not real CLIP
  inference), verify:
  - `GenericHudCollector.capture()` sets `skip_scribe_reason="off_game"` on the returned
    `RawObservation` when the mocked `category_store.for_game(...).classify(...)` returns a
    confident `off_game` `CategoryMatch`.
  - It sets `skip_scribe_reason="none"` when the match isn't confident, or its kind is `"normal"`.
  - `capture()` returns `RawObservation(image=None, ..., skip_scribe_reason="not_foreground")`
    immediately, without calling `screen.capture_bgr()` at all, when
    `screen.rect.is_foreground()` is mocked to return `False`.
  - In `AllyCore.run_turn()`, a `RawObservation` with `skip_scribe_reason="off_game"` results in
    `self.scribe.extract(...)` (mocked) **never being called**, and `self.memory_manager.record_turn`
    (mocked) **never being called** for that turn.
  - A `RawObservation` with `skip_scribe_reason="none"` results in `self.scribe.extract(...)`
    being called, followed by `self.category_store.maybe_learn(...)` being called with the mocked
    Scribe output's `screen_name_guess`.

These three files together should be runnable with `python -m unittest discover tests` and pass
(or skip cleanly on non-Windows for the `window_manager` test) with no live game, no network
access, and no real CLIP model download — everything CLIP-related should be mockable per the
above.

---

## 8. Manual verification checklist (for Ficus, after ZooCode's implementation lands)

Not part of ZooCode's task — listed here so nothing gets forgotten during review:

1. Run Ally against any configured game, alt-tab to a browser mid-session, confirm no Scribe/Ally
   commentary appears about the browser, and commentary resumes once you tab back.
2. Drag the game window to a second monitor mid-session (if available), confirm capture keeps
   working correctly against the new position rather than reading stale coordinates.
3. Check `state/memory.db`'s new `screen_categories` table after a session or two — seed rows
   should be present with `source='seed'`, and at least a few `source='learned'`, `kind='normal'`
   rows should have accumulated from real Scribe output.
4. Watch the logs for the first few sessions to see how often `off_game` actually fires vs. false
   triggers — the confidence/margin thresholds in §3.2 are guesses and will likely need real
   tuning against this feedback, same as every other threshold in this codebase.

---

## Notes for Claude's code review (ZooCode: ignore this entire section)

Things to check carefully when this comes back:

- **Threshold sanity**: the softmax-with-margin approach in `ScreenCategoryStore.query()` is my
  design, not a copy-pasted standard recipe — double check the numerically-stable softmax
  (`exp(scaled - max)`) actually got implemented correctly and doesn't silently produce NaN when
  all scores are very close, and that `np.partition(probs, -2)[-2]` for second-best is correct
  (it should be, but verify against a quick manual trace with 3+ categories).
- **`for_game()` combining global + game rows every call**: confirm this isn't rebuilding/copying
  the global matrix from scratch on every single turn in a way that's actually slow — the `store._rows`
  list itself shouldn't be large, but check the `np.stack` call in `GameScopedView.classify()`
  isn't doing something needlessly expensive if this gets called every turn against a store with a
  couple hundred rows. Should still be sub-millisecond at this scale, but verify ZooCode didn't
  introduce an accidental O(n²) somewhere.
- **The `game_id="__never_matches__"` sentinel trick in `_load_global()`** — I flagged this as
  something ZooCode could clean up with a dedicated query method instead. Check which way they
  went and that it's actually correct either way (global-only rows, no game-scoped leakage).
- **Verify the actual fastembed model names** that got used match something real — I could not
  execute code to confirm `"Qdrant/clip-ViT-B-32-vision"` / `"Qdrant/clip-ViT-B-32-text"` are
  exactly right for whatever fastembed version gets installed; check the summary ZooCode provides
  for what they actually verified.
- **Check the `off_game` narrative-memory exclusion** (§5.3.1) didn't accidentally also exclude
  `low_value` or `not_foreground` cases from `record_turn` — only `off_game` should be excluded;
  the others should record their skip stub exactly as `facts_unchanged` already does today.
- **Check `GenericHudCollector.__init__`'s new optional params default to `None` safely** — any
  existing test or call site that constructs `GenericHudCollector` without the two new args
  (there may be some in the current test suite, not shown in what I reviewed) should still work,
  just with CLIP gating silently disabled (`self.clip_classifier is None` short-circuits the gate
  block in `capture()`).
- **Confirm `ScreenCategoryStore`'s internal lock is actually held around every mutation of
  `self._rows`/`self._matrix`**, not just some of them — I spec'd `maybe_learn` and `_load_global`
  both acquiring it, but double check `for_game()`'s read of `self.store._rows` inside
  `GameScopedView.classify()` is also lock-protected (it reads `self.store._lock` correctly in my
  spec, but this is exactly the kind of thing that's easy to lose during implementation).
- **Watch for whether ZooCode tried to sneak in low_value auto-promotion anyway** — §4.4 was
  explicit about this being deferred; if it shows up, that's scope creep to push back on, however
  well-intentioned.
