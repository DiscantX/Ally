# MTGA Plugin Verification & Testing

This document details how to run verification commands for [`plugins/mtga/`](.) integration. This is the **canonical copy** of the verification-tier table and commands — [`integration_notes.md`](integration_notes.md) links back here rather than repeating it.

## Verification Commands

### 1. Fast Suite (Always Run, No External Dependencies)

Runs all unit and integration test files (`test_*.py`) in [`plugins/mtga/tests/`](tests/):

```bash
python -m unittest discover plugins/mtga/tests -p "test_*.py"
```

*Note:* The real-environment-guarded test cases (such as those in [`plugins/mtga/tests/test_integration_resolution.py`](tests/test_integration_resolution.py:1) and local schema tests in [`plugins/mtga/tests/test_resolver.py`](tests/test_resolver.py:1) which use `skipTest` when Arena or the sample log aren't present) are folded into this fast suite command automatically — they execute successfully or skip cleanly depending on whether local Arena installation files and sample logs are present on the machine.

### 2. Pure Diagnostics (Human Review, Needs Local Arena Install / Sample Log)

Pure diagnostic scripts located in [`plugins/mtga/tests/diagnostics/`](tests/diagnostics/) that print human-readable reports without assertions:

```bash
python plugins/mtga/tests/diagnostics/verify_name_resolution.py
python plugins/mtga/tests/diagnostics/inspect_unresolved.py
python plugins/mtga/tests/diagnostics/test_actual_files.py
python plugins/mtga/tests/diagnostics/verify_parser.py
python plugins/mtga/tests/diagnostics/test_diag.py
```

---

## Open Question / Future Design Consideration

Whether the real-environment test tier and diagnostic scripts (`diagnostics/` folder) should be retained long-term or pruned once the MTGA plugin is considered fully stable remains an **open question** (see [`integration_notes.md`](integration_notes.md) §8). Currently, fixture-based fast tests serve as permanent regression guards, while real-environment integration tests act as periodic drift checks against Arena set releases. Final decision pending ongoing playtesting and stability assessment.