"""Tests for GenreTracker thread safety."""
import threading
import unittest

from brain.state.genre_tracker import GenreTracker


class TestGenreTrackerConcurrency(unittest.TestCase):
    def test_concurrent_updates(self):
        """Verify that GenreTracker handles concurrent update calls safely."""
        tracker = GenreTracker(lock_threshold=0.9)
        errors = []

        def worker():
            for i in range(50):
                try:
                    tracker.update(f"genre_{i % 5}", 0.8 + i * 0.01)
                except Exception as e:
                    errors.append(f"Worker error: {e}")

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent access raised errors: {errors}")

    def test_locking_behavior(self):
        """Verify that GenreTracker locks once confidence exceeds threshold."""
        tracker = GenreTracker(lock_threshold=0.8)
        
        # First update below threshold
        tracker.update("action", 0.7)
        self.assertFalse(tracker.estimate.locked)
        
        # Second update above threshold
        tracker.update("action", 0.85)
        self.assertTrue(tracker.estimate.locked)
        
        # Subsequent updates should not change the estimate
        old_guess = tracker.estimate.guess
        old_confidence = tracker.estimate.confidence
        tracker.update("rpg", 0.95)
        self.assertEqual(tracker.estimate.guess, old_guess)
        self.assertEqual(tracker.estimate.confidence, old_confidence)

    def test_as_context_thread_safety(self):
        """Verify that as_context can be called concurrently with update."""
        tracker = GenreTracker()
        errors = []

        def updater():
            for i in range(50):
                try:
                    tracker.update(f"genre_{i}", 0.5 + i * 0.01)
                except Exception as e:
                    errors.append(f"Updater error: {e}")

        def reader():
            for _ in range(50):
                try:
                    context = tracker.as_context()
                    self.assertIsInstance(context, str)
                except Exception as e:
                    errors.append(f"Reader error: {e}")

        threads = [
            threading.Thread(target=updater) for _ in range(3)
        ] + [
            threading.Thread(target=reader) for _ in range(3)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent access raised errors: {errors}")


if __name__ == "__main__":
    unittest.main()
