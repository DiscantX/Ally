# Plan: Fix TTS/STT and Model Configuration Regressions

## Phase 1: Fix Model Configuration Resolution (`get_model`)

### Step 1.1: Edit [`cabinet/configs/config_manager.py`](cabinet/configs/config_manager.py:139) to Honor Master Model Override
- **Input:** [`cabinet/configs/config_manager.py`](cabinet/configs/config_manager.py:139) `get_model()` function definition.
- **Action:** Update `get_model(key: str, config: dict[str, Any] | None = None) -> str` to check if `use_master_model` is `True` and `master_model` is present in `config`. If so, return `config.get("master_model")` before checking role-specific keys.
- **Expected Output:** [`cabinet/configs/config_manager.py`](cabinet/configs/config_manager.py:139) returns the master model when `use_master_model` is enabled.
- **Error Handling:** If syntax error occurs during edit, stop and ask the user [`cabinet/configs/config_manager.py`](cabinet/configs/config_manager.py:1).

---

## Phase 2: Implement `GeminiTTSProvider`

### Step 2.1: Populate [`infrastructure/tts/providers/gemini_tts_provider.py`](infrastructure/tts/providers/gemini_tts_provider.py:1)
- **Input:** [`infrastructure/tts/providers/gemini_tts_provider.py`](infrastructure/tts/providers/gemini_tts_provider.py:1) (currently contains only placeholder comments).
- **Action:** Write the complete `GeminiTTSProvider` class implementing [`TTSProvider`](infrastructure/tts/base_provider.py:83) and `RetryableProviderMixin`, supporting non-streaming `synthesize()` and streaming `synthesize_stream()` using `google.genai.Client` and `client.interactions.create`, reading `tts_model` and `tts_voice` from user config.
- **Expected Output:** [`infrastructure/tts/providers/gemini_tts_provider.py`](infrastructure/tts/providers/gemini_tts_provider.py:1) defines `GeminiTTSProvider` without import errors.
- **Error Handling:** If `genai` or SDK types differ from Phase 0 findings, stop and ask the user.

---

## Phase 3: Verification & Testing

### Step 3.1: Run Test Suite
- **Input:** Test suite execution command.
- **Action:** Run `python tests/run_tests.py` or unit tests to verify all tests pass successfully.
- **Expected Output:** All unit tests pass with zero import or config resolution failures.
- **Error Handling:** If any test fails, stop and report the traceback to the user.
