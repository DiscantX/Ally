import sys
import unittest

sys.path.insert(0, ".")
from tests.test_save_tracker import TestSaveTracker
from tests.test_run_boundary import TestRunBoundary
from tests.test_cross_session import TestCrossSessionMemory
from tests.test_triggers import TestTriggers, TestNarrativeManagerTriggers
from tests.test_narrative import TestNarrativeMemoryManagerEntryCount
from tests.test_entity_registry_persistence import TestEntityRegistryPersistence
from tests.test_ally import TestAllyAgent
from tests.test_ally_core import TestAllyCore
from tests.test_log_reader import TestLogReaderReplay, TestLogReaderStartAtEnd, TestLogReaderTruncation
from tests.test_lock_correctness import TestChatLockRelease
from tests.test_race_conditions import TestRaceConditions
from tests.test_concurrent_sandbox_and_registry_access import TestConcurrentStateAccess
from tests.test_run_turn_skip_ally import TestRunTurnSkipAlly

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
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestAllyCore))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestLogReaderReplay))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestLogReaderStartAtEnd))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestLogReaderTruncation))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestChatLockRelease))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestRaceConditions))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestConcurrentStateAccess))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestRunTurnSkipAlly))

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
