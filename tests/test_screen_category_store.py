import os
import unittest
from unittest.mock import MagicMock
import numpy as np

from memory.db import MemoryDB
from vision.screen_category_store import ScreenCategoryStore, CategoryMatch
from vision.clip_classifier import ClipClassifier


class TestScreenCategoryStore(unittest.TestCase):
    def setUp(self):
        self.db_path = "state/test_memory_clip.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.db = MemoryDB(db_path=self.db_path)
        
        self.clip_mock = MagicMock(spec=ClipClassifier)
        self.clip_mock.enabled = True
        self.clip_mock.encode_text.return_value = np.array([1.0, 0.0], dtype=np.float32)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_dedup_positive(self):
        store = ScreenCategoryStore(db=self.db, clip=self.clip_mock)
        initial_count = len(store._rows)
        
        # Learn a category
        store.maybe_learn("a battle screen", "game_a")
        count_after_first = len(store._rows)
        
        # Learn a near-identical category
        store.maybe_learn("a battle screen.", "game_a")
        count_after_second = len(store._rows)
        
        self.assertEqual(count_after_first, count_after_second)

    def test_dedup_negative(self):
        store = ScreenCategoryStore(db=self.db, clip=self.clip_mock)
        initial_count = len(store._rows)
        
        store.maybe_learn("combat screen", "game_a")
        count_after_first = len(store._rows)
        
        # Genuinely different phrasing
        store.maybe_learn("inventory and equipment menu", "game_a")
        count_after_second = len(store._rows)
        
        self.assertEqual(count_after_second, count_after_first + 1)

    def test_game_id_scoping(self):
        store = ScreenCategoryStore(db=self.db, clip=self.clip_mock)
        
        # Insert a low_value row scoped to game_a
        self.db.insert_screen_category(
            game_id="game_a", kind="low_value", text="loading screen",
            embedding=np.array([0.5, 0.5], dtype=np.float32).tobytes(), source="learned"
        )
        
        view_a = store.for_game("game_a")
        view_b = store.for_game("game_b")
        
        self.assertTrue(any(r["text"] == "loading screen" for r in view_a.game_rows))
        self.assertFalse(any(r["text"] == "loading screen" for r in view_b.game_rows))

    def test_seed_idempotency(self):
        # First construction (inserts seeds if file exists or mocked)
        store1 = ScreenCategoryStore(db=self.db, clip=self.clip_mock)
        seed_count_1 = self.db.count_screen_categories(source="seed")
        
        # Second construction
        store2 = ScreenCategoryStore(db=self.db, clip=self.clip_mock)
        seed_count_2 = self.db.count_screen_categories(source="seed")
        
        self.assertEqual(seed_count_1, seed_count_2)


if __name__ == "__main__":
    unittest.main()
