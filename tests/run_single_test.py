import unittest
import sys
import os

loader = unittest.TestLoader()
suite = loader.loadTestsFromName("tests.test_ally_core")
runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
