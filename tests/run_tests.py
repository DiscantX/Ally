import sys
import unittest

sys.path.insert(0, ".")
from tests.test_save_tracker import TestSaveTracker
from tests.test_run_boundary import TestRunBoundary
from tests.test_cross_session import TestCrossSessionMemory
from tests.test_triggers import TestTriggers, TestNarrativeManagerTriggers
from tests.test_narrative import TestNarrativeMemoryManagerEntryCount
from state.test_entity_registry_persistence import TestEntityRegistryPersistence
from ally.test_ally import TestAllyAgent

if __name__ == "__main__":
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestSaveTracker))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestRunBoundary))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestCrossSessionMemory))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestTriggers))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestNarrativeManagerTriggers))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestNarrativeMemoryManagerEntryCount))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestEntityRegistryPersistence))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestAllyAgent))

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
