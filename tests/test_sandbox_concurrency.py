"""Tests for StateSandbox thread safety."""
import threading
import unittest

from brain.state.sandbox import StateSandbox
from brain.knowledge.schema.schema import ScreenElement
from ingestion.collectors.base import ConfirmedFact


class TestSandboxConcurrency(unittest.TestCase):
    def test_concurrent_update_and_read(self):
        """Verify that StateSandbox handles concurrent update and read operations safely."""
        sandbox = StateSandbox()
        errors = []

        def writer():
            for i in range(100):
                try:
                    el = ScreenElement(id=f"el_{i}", label=f"thing_{i}", description=f"desc_{i}", box_2d=[0, 0, 1, 1])
                    fact = ConfirmedFact(key=f"fact_{i}", value=f"val_{i}", source="test")
                    sandbox.update([el], [fact])
                except Exception as e:
                    errors.append(f"Writer error: {e}")

        def reader():
            for i in range(100):
                try:
                    context = sandbox.as_context()
                    # Just verify we can read without crashing
                    self.assertIsInstance(context, str)
                except Exception as e:
                    errors.append(f"Reader error: {e}")

        threads = [
            threading.Thread(target=writer) for _ in range(5)
        ] + [
            threading.Thread(target=reader) for _ in range(5)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent access raised errors: {errors}")

    def test_turn_counter_consistency(self):
        """Verify that turn counter increments correctly under concurrent access."""
        sandbox = StateSandbox()
        num_threads = 10
        updates_per_thread = 50
        expected_turns = num_threads * updates_per_thread

        def worker():
            for _ in range(updates_per_thread):
                sandbox.update([], [])

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sandbox.turn, expected_turns)

    def test_structured_state_persistence(self):
        """Verify that structured_state persists across updates when not provided."""
        sandbox = StateSandbox()
        
        # First update with structured_state
        structured = {"key1": "value1", "key2": {"nested": "value2"}}
        sandbox.update([], [], structured_state=structured, structured_state_source="test")
        
        # Second update without structured_state - should preserve it
        sandbox.update([], [])
        
        # Verify structured_state is still there
        self.assertEqual(sandbox.structured_state, structured)
        self.assertEqual(sandbox.structured_state_source, "test")
        
        # Third update with new structured_state - should replace it
        new_structured = {"key3": "value3"}
        sandbox.update([], [], structured_state=new_structured, structured_state_source="test2")
        
        self.assertEqual(sandbox.structured_state, new_structured)
        self.assertEqual(sandbox.structured_state_source, "test2")


if __name__ == "__main__":
    unittest.main()
