# Test Suite Documentation

This directory contains unit tests, integration tests, and verification modules for [`Ally`](main.py:1). The test suite ensures core functionality, memory management, concurrency safety, triggers, and state persistence behave correctly.

## Running Tests

To run the test suite, you can execute the test runner script:

```bash
python tests/run_tests.py
```

Alternatively, you can use unittest discovery from the root directory:

```bash
python -m unittest discover tests
```

## Test Modules

- [`run_tests.py`](tests/run_tests.py:1): Test runner aggregating and executing core test suites.
- [`test_ally.py`](tests/test_ally.py:1): Unit tests for [`AllyAgent`](ally/ally_agent.py:1) behavior and decisions.
- [`test_ally_core.py`](tests/test_ally_core.py:1): Tests for core system initialization and operational components.
- [`test_clip_gate_integration.py`](tests/test_clip_gate_integration.py:1): Test module.
- [`test_concurrent_sandbox_and_registry_access.py`](tests/test_concurrent_sandbox_and_registry_access.py:1): Concurrency tests verifying thread safety across sandbox and entity registry operations.
- [`test_cross_session.py`](tests/test_cross_session.py:1): Tests for cross-session state merging and persistence.
- [`test_entity_registry_persistence.py`](tests/test_entity_registry_persistence.py:1): Tests for entity registry serialization and database persistence.
- [`test_lock_correctness.py`](tests/test_lock_correctness.py:1): Verification of locking mechanisms and thread synchronization correctness.
- [`test_log_reader.py`](tests/test_log_reader.py:1): Tests for log reading and event parsing capabilities.
- [`test_models.py`](tests/test_models.py:1): Tests for model configuration and data structures.
- [`test_narrative.py`](tests/test_narrative.py:1): Unit tests for NarrativeMemoryManager entry count and cadence handling.
- [`test_race_conditions.py`](tests/test_race_conditions.py:1): Race condition diagnostic and concurrency checks.
- [`test_run_boundary.py`](tests/test_run_boundary.py:1): Tests for run boundaries and session lifecycle management.
- [`test_run_turn_skip_ally.py`](tests/test_run_turn_skip_ally.py:1): Tests verifying turn skipping and execution flow.
- [`test_save_tracker.py`](tests/test_save_tracker.py:1): Tests for tracking save files and change detection.
- [`test_screen_category_store.py`](tests/test_screen_category_store.py:1): Test module.
- [`test_triggers.py`](tests/test_triggers.py:1): Tests for trigger evaluation and event-driven memory updates.
- [`test_window_manager_refresh.py`](tests/test_window_manager_refresh.py:1): Test module.

---

*Note: Test files are automatically indexed and updated via [`tools/update_docs.py`](tools/update_docs.py:1).*
