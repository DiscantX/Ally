import unittest
import sys

print("=== RUNNING tests.test_ally_core ===")
suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_ally_core")
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
status = "SUCCESS" if result.wasSuccessful() else "FAILURE"
with open("test_1_status.txt", "w") as f:
    f.write(status)
print(f"Test run completed with status: {status}")
sys.exit(0 if result.wasSuccessful() else 1)
