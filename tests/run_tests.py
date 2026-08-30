import sys
import unittest

sys.path.insert(0, ".")
from tests.test_save_tracker import TestSaveTracker
from tests.test_run_boundary import TestRunBoundary
from tests.test_cross_session import TestCrossSessionMemory
from tests.test_triggers import TestTriggers, TestNarrativeManagerTriggers, TestSignificantMomentTrigger
from tests.test_personality_journal_split import TestPersonalityJournalSplit
from tests.test_narrative import TestNarrativeMemoryManagerEntryCount
from tests.test_entity_registry_persistence import TestEntityRegistryPersistence
from tests.test_ally import TestAllyAgent
from tests.test_ally_core import TestAllyCore
from tests.test_log_reader import TestLogReaderReplay, TestLogReaderStartAtEnd, TestLogReaderTruncation
from tests.test_lock_correctness import TestChatLockRelease
from tests.test_race_conditions import TestRaceConditions
from tests.test_concurrent_sandbox_and_registry_access import TestConcurrentStateAccess
from tests.test_run_turn_skip_ally import TestRunTurnSkipAlly
from tests.test_screen_category_store import TestScreenCategoryStore
from tests.test_window_manager_refresh import TestWindowManagerRefresh
from tests.test_clip_gate_integration import TestClipGateIntegration
from tests.test_event_hook import TestEventHook
from tests.test_turn_trace import TestTurnTrace
from tests.test_shell_bounds_registry import TestShellBoundsRegistry
from tests.test_logger_pubsub import TestLoggerPubSub
from tests.test_perspective_engine import TestPerspectiveEngine
from tests.test_gemini_provider_stream_field import TestGeminiProviderStreamField
from tests.test_ally_stream import TestAllyStream
from tests.test_provider_router import TestProviderRouter

if __name__ == "__main__":
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestSaveTracker))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestRunBoundary))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestCrossSessionMemory))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestTriggers))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestNarrativeManagerTriggers))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestSignificantMomentTrigger))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestPersonalityJournalSplit))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestNarrativeMemoryManagerEntryCount))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestEntityRegistryPersistence))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestAllyAgent))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestAllyCore))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestLogReaderReplay))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestRunReaderStartAtEnd if hasattr(sys, 'RunReaderStartAtEnd') else TestLogReaderStartAtEnd))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestLogReaderStartAtEnd))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestLogReaderTruncation))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestChatLockRelease))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestRaceConditions))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestConcurrentStateAccess))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestRunTurnSkipAlly))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestScreenCategoryStore))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestWindowManagerRefresh))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestClipGateIntegration))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestEventHook))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestTurnTrace))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestShellBoundsRegistry))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestLoggerPubSub))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestPerspectiveEngine))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGeminiProviderStreamField))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestAllyStream))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestProviderRouter))

    with open("test_results.log", "w") as log_file:
        runner = unittest.TextTestRunner(stream=log_file, verbosity=2)
        result = runner.run(suite)
    print("Tests finished. Result success:", result.wasSuccessful())
    sys.exit(0 if result.wasSuccessful() else 1)
