# Ally Call Optimization Plan

This document outlines proposed optimizations to speed up the Ally LLM call (`Ally.decide()` in [`ally/ally_agent.py`](ally/ally_agent.py:26)) and reduce overall pipeline latency.

---

## Proposed Optimizations

### 1. Reduce Thinking Level

* **Target File**: [`ally/ally_agent.py`](ally/ally_agent.py:45)
* **Description**: Currently set to `thinking_level="HIGH"`. Lowering this to `"MEDIUM"` or `"MINIMAL"` (matching [`interpretation/scribe.py`](interpretation/scribe.py:28)) or making it configurable via settings will significantly reduce generation latency.

### 2. Context & Memory Token Limits

* **Target Files**: [`memory/manager.py`](memory/manager.py:22), [`memory/narrative.py`](memory/narrative.py:1)
* **Description**: Adjust `short_term_capacity` (currently default `8` turns) and implement stricter truncation/summarization of past narrative context and entity registries passed to Ally.

### 3. Element Filtering in State Sandbox

* **Target Files**: [`state/sandbox.py`](state/sandbox.py:1), [`ally/ally_agent.py`](ally/ally_agent.py:26)
* **Description**: Filter out static, decorative, or non-actionable UI elements from `elements_context` so the model processes fewer input tokens per turn.

### 4. Semantic Diff Guard

* **Target Files**: [`vision/change_detector.py`](vision/change_detector.py:19), [`main.py`](main.py:224)
* **Description**: Beyond pixel-level SSIM change detection, implement a semantic diff check on `sandbox.as_context()`. If visual changes occur due to ambient particles/animations but the underlying extracted game state/text is identical, bypass the Ally LLM call.

### 5. Streamline Prompts and Pydantic Schemas

* **Target Files**: [`prompts/ally.py`](prompts/ally.py:1), [`schema/schema.py`](schema/schema.py:1)
* **Description**: Remove verbose boilerplate in [`ALLY_PROMPT_TEMPLATE`](prompts/ally.py:1) and streamline the JSON output schema to minimize generation overhead.

### 6. Asynchronous Pipeline Execution

* **Target Files**: [`main.py`](main.py:211)
* **Description**: Offload Scribe and Ally LLM inference calls into a background worker thread (`ThreadPoolExecutor`) or async worker to prevent blocking the main capture loop and UI overlay.

### 7. GUI Settings Integration

* **Target Files**: [`gui/settings_window.py`](gui/settings_window.py:106), [`configs/config_manager.py`](configs/config_manager.py:1)
* **Description**: Add thinking level dropdowns and threshold controls to the Advanced/Dev tab in the Settings UI so users can tune performance parameters at runtime.
