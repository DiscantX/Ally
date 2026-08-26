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

SEED_FILE = "configs/template/clip_seed_categories.json"


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
        self.skip_confidence_threshold = config.get("clip_skip_confidence_threshold", 0.5)
        self.skip_margin_threshold = config.get("clip_skip_margin_threshold", 0.15)
        self.dedup_threshold = config.get("clip_category_dedup_threshold", 0.75)

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
