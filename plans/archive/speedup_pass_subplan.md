# Speedup Pass Sub-plan (Items 2.2–2.7)

This sub-plan addresses Pass 2 items 2.2 through 2.7 from the speedup plan, providing detailed design steps for each optimization. These items assume Pass 1 (memory correctness) is already verified and in place.

---

## 2.2: Context & Memory Token Limits

**Goal**: Tune buffer size and flush interval independently after Pass 1 Steps 5/6 decoupled `short_term_capacity` from flush cadence. The goal is to reduce token count per Ally call without sacrificing meaningful context.

**Key changes**:

- **`memory/manager.py`**: Ensure `MemorySystem.__init__` accepts and passes through `medium_flush_interval` as a separate parameter from `short_term_capacity` (already done in Pass 1 Step 5). The default `medium_flush_interval` should be 8 turns (same as current `short_term_capacity` default, but conceptually distinct — flush can happen at interval even if buffer not full, and buffer can fill before interval).

- **`memory/narrative.py`**: Implement stricter truncation/summarization of past narrative context passed to Ally. When `build_context()` constructs the memory summary:
  - If `short_term_capacity` entries exceed the buffer, summarize the oldest entries into a single "earlier context" bullet before the recent entries.
  - Entity registry context should also be truncated to the most recent N entities, with a note like "…and X earlier entities" if truncated.
  - Ensure the total token count of the memory_context string passed to `ally.decide()` stays within a sensible range (target: under ~1500 tokens for typical scenes).

- **`memory/personality.py`**: Similarly truncate personality journal context if it exceeds a reasonable token budget.

- **Decision**: Keep `short_term_capacity` as the *maximum* number of turn entries retained in the rolling buffer, and `medium_flush_interval` as the *maximum* turns between automatic flushes even if the buffer isn't full. This allows independent tuning: a developer can set a large `short_term_capacity` with a small `medium_flush_interval` to flush frequently with minimal context, or a small capacity with a large interval for deeper context per call.

**Todo**: [ ] Review `memory/narrative.py` `build_context()` method and add truncation with summary fallback. [ ] Review `memory/personality.py` and add similar truncation. [ ] Verify `memory/manager.py` passes `medium_flush_interval` correctly.

---

## 2.3: Element Filtering in State Sandbox

**Goal**: Reduce the number of UI elements presented to Ally by filtering out decorative/non-actionable elements, while ensuring nothing an action could reference is dropped. The caution from the speedup plan is explicit: filtering must not drop anything an action could point to via `target_entity_ids`.

**Key changes**:

- **`schema/schema.py`**: Add an `is_decorative: bool` field to `ScreenElement` (default `False`). This allows Scribe to flag elements that are purely decorative.

- **`prompts/scribe.py`** (`SCRIBE_PROMPT_UI`): Add instruction to Scribe to mark elements as decorative when they are purely visual/UI with no functional role. Example instruction addition:
  > "If an element is purely decorative (e.g., background art, non-interactive icon, ambient decoration) with no text, no clickable action, and no role in gameplay, set `is_decorative` to `true`. Decorative elements will be filtered out by the pipeline before Ally sees them, but nothing an action could reference will be marked decorative."

- **`state/sandbox.py`** (`StateSandbox`): After `update()` and before `as_context()`, add a filtering step that removes elements where `is_decorative` is `True`. The filter should:
  - Keep all elements where `is_decorative` is `False` or `None` (default).
  - **Critical constraint**: Before marking any element as `is_decorative=True`, verify it cannot be referenced by any existing `target_entity_ids` in the current Ally output from the previous turn. If there's any risk, keep the element.

- **`ally/ally_agent.py`** (`Ally.decide()`): No direct changes needed — the filtering happens in the sandbox before the context string is built. However, ensure `AllyOutput.target_entity_ids` references are preserved even when decorative elements are stripped.

- **Safety approach**: Prefer filtering only elements Scribe itself could plausibly flag as decorative (using the `is_decorative` bool) over a generic heuristic applied after the fact with no signal from Scribe about what's safe to drop. The `is_decorative` flag in the Scribe schema provides the signal needed for safe post-processing.

**Todo**: [ ] Add `is_decorative: bool = False` to `ScreenElement` in `schema/schema.py`. [ ] Add Scribe prompt instruction to set `is_decorative` for purely visual elements in `prompts/scribe.py`. [ ] Add filtering logic in `state/sandbox.py` `as_context()` to strip decorative elements safely. [ ] Verify `AllyOutput.target_entity_ids` references are preserved after filtering.

---

## 2.4: Semantic Diff Guard

**Goal**: Implement the semantic diff guard already flagged in the decision log — `GenericHudCollector` retains last turn's `ConfirmedFacts`, compares this turn's against last turn's, and if identical, skips invoking Scribe/Ally for this turn even if SSIM detected pixel-level motion.

**Key changes**:

- **`collectors/configured_collector.py`** (`GenericHudCollector`):
  - Add instance variable `self._last_confirmed_facts: list[ConfirmedFact] = []` initialized in `__init__`.
  - In `capture()`, after obtaining `confirmed_facts` from the reader, compare the current list against `self._last_confirmed_facts`:
    - If the lists are identical (same keys and values in same order), set a flag `skip_ally = True` on the `RawObservation` or return early with a modified observation.
    - If different, update `self._last_confirmed_facts = confirmed_facts` and proceed normally.
  - If `skip_ally` is True, still update the sandbox with the current elements/confirmed_facts so the state stays consistent, but skip the Scribe extraction and Ally decision for this turn.

- **`main.py`** (`run_turn`): Check for the skip condition. If the observation indicates `skip_ally` or equivalent, bypass the Scribe call (`scribe.extract()`) and Ally call (`ally.decide()`), but still:
  - Update the sandbox with current elements.
  - Update the genre tracker.
  - Update the entity registry (if elements changed).
  - Increment the memory counter via `memory_manager.record_turn()` so the flush cadence still works.
  - The skip only prevents the LLM call, not the entire turn processing.

- **Note on scope**: This only helps calibrated-OCR games where `ConfirmedFacts` exist (i.e., the collector has a layout/reader that can read exact values). For uncalibrated screens (no reader), `confirmed_facts` will be empty, so the diff check is a no-op — this is expected and documented. For MTGA's `structured_state` path, a different diff check on accumulated game state would be needed, which is a separate scope item.

**Todo**: [ ] Add `self._last_confirmed_facts` to `GenericHudCollector.__init__`. [ ] Add diff comparison logic in `GenericHudCollector.capture()`. [ ] Modify `RawObservation` or add a mechanism to signal skip_ally. [ ] Update `main.py` `run_turn()` to check for skip and bypass Scribe/Ally calls while maintaining state consistency. [ ] Add tests for the diff guard: same facts → skip; different facts → proceed; empty facts → no-op.

---

## 2.5: Streamline Prompts and Schemas

**Goal**: Trim genuinely redundant wording in `ALLY_PROMPT_TEMPLATE` while strictly preserving the FTL-specific behaviors that fix real observed bugs. Do not do a wholesale rewrite.

**Key changes** — trim only the following genuinely redundant or repetitive wording from `ALLY_PROMPT_TEMPLATE` in `prompts/ally.py`:

- Remove any phrasing that repeats the "natural name" / "no brackets" / "opinionated" rules in multiple places.
- Consolidate the "have an opinion, don't just list options neutrally" instruction into a single concise statement.
- Remove boilerplate that doesn't affect output behavior (e.g., introductory filler that models tend to ignore anyway).

**Critical preservation** — must strictly preserve these FTL-observed behaviors (verify output after each change):

1. **No brackets outside the actions list**: Analysis text must never contain `[`/`]` except in the designated actions list.
2. **Proper names not "Crew Member X"**: People must be referred by their natural name (e.g., "Dolan"), not by UI labels or generic placeholders.
3. **"Have an opinion, don't just list options neutrally"**: Ally must state what it would actually do and why, not present choices neutrally.
4. **Natural naming instead of raw UI labels**: Elements referred to in analysis must use natural names, not screen element labels.

**Change process**:

1. Create a trimmed version of `ALLY_PROMPT_TEMPLATE` with only the non-redundant portions.
2. Run existing FTL test cases (or mock-provider tests) against both the original and trimmed prompts.
3. Compare outputs for each of the 4 critical behaviors above.
4. If any behavior is lost, restore the minimal necessary wording.
5. Iterate until the prompt is trimmed as much as possible while all 4 behaviors are preserved.

**Todo**: [ ] Identify redundant wording in `ALLY_PROMPT_TEMPLATE` that can be safely removed. [ ] Create trimmed prompt version. [ ] Run verification against FTL behaviors (no brackets outside actions, proper names, opinionated, natural naming). [ ] Iterate until trim is maximal while behaviors preserved. [ ] Update `prompts/ally.py` with the final trimmed prompt.

---

## 2.6: Asynchronous Pipeline Execution

**Goal**: Offload Scribe and Ally LLM inference calls into a background worker thread using `ThreadPoolExecutor`, with `threading.Lock` as a blocking prerequisite. This is the highest-risk item and must be done last.

**Prerequisite — Locking layer** (must complete before any threading):

- **`memory/manager.py`** / shared state: Add a single `threading.Lock` instance to `MemorySystem` (or `MemoryManager`) that guards every read-modify-write sequence against `sandbox`, `registry`, and `memory_manager` from *any* thread, including the existing GUI chat thread.
  - The lock should be acquired before any mutation of shared state and released after.
  - All code paths that access `sandbox`, `registry`, or `memory_manager` from multiple threads must use this same lock.
  - Write this as its own verifiable sub-plan first — create a simple test that spawns two threads accessing shared state through the lock, confirming no race conditions.

- **Existing chat thread** (`main.py` `on_send_message`): The GUI chat handler already runs `ally.chat()` on a background `threading.Thread`. This thread must acquire the same lock before reading/writing shared state.

**Step 1 — Locking** (complete and test in isolation):

1. Add `self._state_lock = threading.Lock()` to `MemorySystem.__init__`.
2. Wrap all read-modify-write operations on `sandbox`, `registry`, and `memory_manager` with `with self._state_lock:`.
3. Test: Create a unit test that spawns two threads — one simulating the main loop `run_turn()` and one simulating the chat `on_send_message` — both accessing the same `MemorySystem` instance through the lock. Verify no corruption.

**Step 2 — ThreadPoolExecutor** (after locking is verified):

1. Create a `ThreadPoolExecutor` (max_workers=2 or reasonable) within `MemorySystem` or the main loop.
2. Offload `scribe.extract()` and `ally.decide()` / `ally.chat()` calls to the executor.
3. On completion (via `future.add_done_callback` or `future.result()`), acquire the same lock and update shared state (`sandbox`, `registry`, `memory_manager`).
4. Ensure the main capture loop continues without blocking while LLM inference runs in the background.

**Decision note**: If a lock-per-object model proves error-prone, prefer a single-writer queue pattern: all mutations to shared state happen on one dedicated thread, and other threads (main loop, chat thread) submit work items to it. This matches the project's preference for simple, obviously-correct mechanisms over clever ones.

**Todo**: [ ] Add `threading.Lock` to `MemorySystem` and wrap all shared-state access. [ ] Write and run a concurrency test with two threads (main loop + chat) accessing shared state through the lock. [ ] Only after lock is verified, add `ThreadPoolExecutor` for Scribe/Ally inference offloading. [ ] Ensure GUI chat thread also uses the lock.

---

## 2.7: GUI Settings Integration

**Goal**: Before adding new controls (e.g., thinking-level dropdown), fix the existing gap where `gui/settings_window.py` writes a full settings dict to `configs/user_config.json` via `save_user_config()`, but only `enable_downscaling` / `downscale_max_size` are actually read anywhere. Every other key — model selections, `default_personality`, ChangeDetector/ScreenClassifier/ScreenBootstrapper thresholds — is currently write-only.

**Key changes** — make all construction sites read tunable values from `load_user_config()` with hardcoded values as fallback defaults:

- **`configs/config_manager.py`**: The `load_user_config()` function already exists and loads from `configs/user_config.json` with `DEFAULT_USER_CONFIG` as fallback. This is the single source of truth.

- **`collectors/screen_collector.py`**: Already reads `enable_downscaling` and `downscale_max_size` from config. Verify these are read via `load_user_config()`.

- **`interpretation/scribe.py`** (`Scribe.__init__`): Accept optional config dict or read from `load_user_config()`:
  - `thinking_level` parameter (currently hardcoded as `"minimal"` in the `extract()` call — actually in `scribe.py` line 28, the `extract()` method passes `thinking_level="minimal"` directly to `provider.generate_structured()`. Make this read from config with a default of `"minimal"`.
  - Actually, looking at the code, `thinking_level` is passed directly in `extract()`, not stored on the Scribe instance. For 2.1 (reduce thinking level), the `Ally` class already has `thinking_level` as a constructor parameter. For Scribe, we may need to pass it through or make the `extract()` method read from config.

- **`ally/ally_agent.py`** (`Ally.__init__`): Already has `thinking_level: str = "LOW"` as a constructor parameter (Pass 1 Step 1). This is the thinking-level control needed for 2.1. Ensure it reads from config or has a sensible default.

- **`memory/manager.py`** (`MemorySystem.__init__`): Pass relevant config values to `NarrativeMemoryManager` and `PersonalityMemoryManager`:
  - `short_term_capacity` — already passed.
  - `medium_flush_interval` — already passed per Pass 1 Step 5.
  - Any new tunable thresholds from config.

- **`state/entity_registry.py`** (`EntityRegistry.__init__`): Accept and read config values for any entity-resolution thresholds.

- **`state/genre_tracker.py`** (`GenreTracker.__init__`): Read thresholds from config.

- **`vision/change_detector.py`** (`ChangeDetector.__init__`): Read `threshold_percent`, `pixel_diff_threshold`, `major_change_threshold`, `stability_threshold_percent`, `use_ssim` from config.

- **`vision/screen_classifier.py`** (`ScreenClassifier.__init__`): Read `match_threshold`, `draft_match_threshold` from config.

- **`vision/screen_bootstrapper.py`** (`ScreenBootstrapper.__init__`): Read `unknown_streak_threshold` from config.

- **GUI additions** (after all construction sites read from config):
  - Add a "Thinking Level" dropdown to the Advanced/Dev tab in `gui/settings_window.py` with options: LOW, MEDIUM, HIGH.
  - When changed, update the relevant objects' `thinking_level` attribute and save to config.
  - The thinking-level control now actually does something because all downstream objects read from the same config.

**Todo**: [ ] Verify all construction sites (scribe, ally, narrative, personality, change_detector, screen_classifier, screen_bootstrapper, entity_registry) read their tunable values from `load_user_config()` with proper fallbacks. [ ] Add thinking-level dropdown to `gui/settings_window.py` Advanced/Dev tab. [ ] Ensure the dropdown updates thinking_level in all relevant objects and saves to config. [ ] Test end-to-end: change thinking level via GUI, verify it affects Ally/Scribe behavior.

---

## Summary of All 2.2–2.7 Items

| Item | Core Focus | Key Files |
| ------ | ----------- | ----------- |
| **2.2** | Context & memory token limits | `memory/manager.py`, `memory/narrative.py`, `memory/personality.py` |
| **2.3** | Element filtering in State Sandbox | `schema/schema.py`, `prompts/scribe.py`, `state/sandbox.py`, `ally/ally_agent.py` |
| **2.4** | Semantic diff guard | `collectors/configured_collector.py`, `main.py` |
| **2.5** | Streamline prompts and schemas | `prompts/ally.py` |
| **2.6** | Asynchronous pipeline execution | `memory/manager.py` (lock), `main.py` (ThreadPoolExecutor) |
| **2.7** | GUI settings integration | `gui/settings_window.py`, `configs/config_manager.py`, all construction sites |

**Execution order**: 2.2 → 2.3 → 2.4 → 2.5 → 2.6 (locking first, then ThreadPoolExecutor) → 2.7. Items 2.6 and 2.7 have dependencies — locking must be verified before threading, and config integration should be largely complete before adding GUI controls.
