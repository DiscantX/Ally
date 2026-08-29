import unittest
import threading
from brain.state.shell_bounds_registry import ShellBoundsRegistry

class TestShellBoundsRegistry(unittest.TestCase):
    def test_registry_basic(self):
        reg = ShellBoundsRegistry()
        reg.update("shell_1", 10, 20, 100, 200)
        reg.update("shell_2", 50, 60, 300, 400)
        bounds = reg.all_bounds()
        self.assertEqual(len(bounds), 2)
        self.assertIn((10, 20, 100, 200), bounds)
        self.assertIn((50, 60, 300, 400), bounds)

        reg.unregister("shell_1")
        self.assertEqual(reg.all_bounds(), [(50, 60, 300, 400)])

    def test_thread_safety(self):
        reg = ShellBoundsRegistry()
        errors = []

        def worker(idx):
            try:
                for i in range(100):
                    reg.update(f"shell_{idx}_{i}", i, i, 50, 50)
                    reg.all_bounds()
                    reg.unregister(f"shell_{idx}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        self.assertEqual(errors, [])
