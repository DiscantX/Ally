import threading
import time
import unittest
import sys
import os

# Add the project root to sys.path to allow importing from main and other modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import STATE_LOCK
from state.entity_registry import EntityRegistry, ResolvableElement

class TestRaceConditions(unittest.TestCase):
    def test_shared_state_locking(self):
        """Verify that STATE_LOCK prevents race conditions on shared data."""
        shared_data = {"count": 0}
        num_threads = 10
        increments_per_thread = 1000
        
        def worker():
            for _ in range(increments_per_thread):
                with STATE_LOCK:
                    current = shared_data["count"]
                    # No sleep, just count
                    shared_data["count"] = current + 1
        
        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        expected = num_threads * increments_per_thread
        self.assertEqual(shared_data["count"], expected, f"Race condition detected! Expected {expected}, got {shared_data['count']}")
        print(f"Test passed: {shared_data['count']} increments completed successfully.")

    def test_entity_registry_concurrency(self):
        """Verify that EntityRegistry handles concurrent resolve_or_create calls safely."""
        registry = EntityRegistry()
        num_threads = 5
        items_per_thread = 50

        def worker(thread_idx):
            for i in range(items_per_thread):
                el = ResolvableElement(
                    label=f"Entity_{thread_idx}_{i}",
                    description=f"Desc {i}",
                    external_id=f"ext_{thread_idx}_{i}",
                    entity_type="test"
                )
                registry.resolve_or_create([el], turn=1)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(registry._entities), num_threads * items_per_thread)

if __name__ == "__main__":
    unittest.main()
