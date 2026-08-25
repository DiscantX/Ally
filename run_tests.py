import sys
import unittest

sys.path.insert(0, ".")
from memory.test_save_tracker import TestSaveTracker
from memory.test_run_boundary import TestRunBoundary
from memory.test_cross_session import TestCrossSessionMemory
from memory.test_triggers import TestTriggers, TestNarrativeManagerTriggers
from memory.test_narrative import TestNarrativeMemoryManagerEntryCount
from state.test_entity_registry_persistence import TestEntityRegistryPersistence

if __name__ == "__main__":
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestSaveTracker))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestRunBoundary))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestCrossSessionMemory))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestTriggers))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestNarrativeManagerTriggers))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestNarrativeMemoryManagerEntryCount))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestEntityRegistryPersistence))

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
