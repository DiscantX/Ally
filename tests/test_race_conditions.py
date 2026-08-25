import threading
import time
import unittest
import sys
import os

# Add the project root to sys.path to allow importing from main and other modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import STATE_LOCK

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

if __name__ == "__main__":
    unittest.main()
