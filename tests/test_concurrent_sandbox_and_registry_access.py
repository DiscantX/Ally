# test_concurrent_state_access.py
import threading
import unittest

from brain.state.sandbox import StateSandbox
from brain.state.entity_registry import EntityRegistry
from brain.knowledge.schema.schema import ScreenElement


class TestConcurrentStateAccess(unittest.TestCase):
    def test_concurrent_sandbox_and_registry_access(self):
        sandbox = StateSandbox()
        registry = EntityRegistry()
        errors = []

        def hammer_capture():
            for i in range(200):
                try:
                    el = ScreenElement(id=f"el_{i}", label=f"thing_{i}", description="x", box_2d=[0, 0, 1, 1])
                    sandbox.update([el], [])
                    registry.resolve_or_create([el], sandbox.turn)
                except Exception as e:
                    errors.append(e)

        def hammer_chat_reads():
            for i in range(200):
                try:
                    _ = sandbox.as_context()
                    _ = registry.as_context(list(registry._entities.values()))
                except Exception as e:
                    errors.append(e)

        threads = (
            [threading.Thread(target=hammer_capture) for _ in range(2)]
            + [threading.Thread(target=hammer_chat_reads) for _ in range(2)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent access raised: {errors}")


if __name__ == "__main__":
    unittest.main()