"""Smoke test runner for VoiceInputController unit tests."""
import sys
sys.path.insert(0, ".")

# Set up a QApplication before importing the controller
from PySide6.QtCore import QCoreApplication
app = QCoreApplication.instance()
if app is None:
    app = QCoreApplication([])

# Now run the test
import unittest

loader = unittest.TestLoader()
try:
    suite = loader.loadTestsFromName("tests.test_voice_input_controller.TestVoiceInputController")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print(f"\nTest success: {result.wasSuccessful()}")
    sys.exit(0 if result.wasSuccessful() else 1)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"\nFATAL: {e}")
    sys.exit(2)
