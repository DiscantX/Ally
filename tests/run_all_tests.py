import unittest
import sys

test_files = [
    "tests.test_ally_core",
    "tests.test_ally_core_concurrency",
    "tests.test_lock_correctness"
]

results = {}
for test_name in test_files:
    print(f"=== RUNNING {test_name} ===")
    try:
        suite = unittest.defaultTestLoader.loadTestsFromName(test_name)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        results[test_name] = result.wasSuccessful()
    except Exception as e:
        print(f"Error running {test_name}: {e}")
        results[test_name] = False

print("\n=== SUMMARY ===")
for test_name, success in results.items():
    print(f"{test_name}: {'SUCCESS' if success else 'FAILURE'}")

sys.exit(0 if all(results.values()) else 1)
