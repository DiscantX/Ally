import unittest
import traceback
import sys

try:
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_ally_core_concurrency")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    with open("test_2_status.txt", "w") as f:
        f.write("SUCCESS" if result.wasSuccessful() else "FAILURE")
    if not result.wasSuccessful():
        with open("test_2_error.txt", "w") as f:
            for failure in result.failures:
                f.write(str(failure[0]) + "\n" + str(failure[1]) + "\n\n")
            for error in result.errors:
                f.write(str(error[0]) + "\n" + str(error[1]) + "\n\n")
except Exception as e:
    with open("test_2_error.txt", "w") as f:
        traceback.print_exc(file=f)
    with open("test_2_status.txt", "w") as f:
        f.write("FAILURE")
