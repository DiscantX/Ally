# Sub-Plan: Pass 1 Step 3 & Step 4 — Ally-Detected Run Boundary and Genuine Cross-Session Memory Tier

## Overview

This sub-plan specifies the detailed implementation plan for **Pass 1 Step 3 (Ally-detected run boundary)** and **Pass 1 Step 4 (Genuine cross-session memory tier)**. It enables Ally to semantically recognize run boundaries (victory, defeat, game over) when visual indicators appear, resolve run closure priorities between native collector signals and Ally semantic outputs, record cross-session summaries in a dedicated SQLite table (`cross_session_memory`), synthesize cross-session histories via LLM (`CROSS_SESSION_SUMMARY_PROMPT`), and wire run closure into `main.py`.

---

## 1. Schema Addition (`schema/schema.py`)

Add `run_boundary` field to `AllyOutput`:

```python
class AllyOutput(BaseModel):
    analysis: str
    actions: list[ActionItem]
    run_boundary: Literal["none", "run_ended"] = "none"
```

---

## 2. Prompt Additions (`prompts/ally.py` & `prompts/narrative.py`)

### A. Ally Prompt (`prompts/ally.py`)

Add instructions to `ALLY_PROMPT_TEMPLATE`:

```text
"If the current screen is an unambiguous end-of-run screen — victory, defeat, game over, run complete — set run_boundary to 'run_ended'. Only do this for a genuine terminal screen, not a story beat, cutscene, or dialogue that merely sounds final. When in doubt, use 'none'."
```

### B. Cross-Session Summary Prompt (`prompts/narrative.py`)

Add `CROSS_SESSION_SUMMARY_PROMPT`:

```python
CROSS_SESSION_SUMMARY_PROMPT = (
    "You are Ally. Review the previous cross-session summary and the just-completed run's long-term overview to synthesize an updated, high-level cross-session summary for this game.\n\n"
    "Previous cross-session summary:\n{prior_cross_session}\n\n"
    "Just-completed run summary:\n{just_finished_run}\n\n"
    "Synthesize these into a single cohesive, high-level cross-session summary focusing on what we generally know about this game, persistent meta-strategies, and how runs tend to go. Do not give a blow-by-blow of the just-finished run."
)
```

---

## 3. Priority Resolution Function & Run Boundary (`memory/triggers.py` or separate module / helper)

Create or place `resolve_run_ended(observation, ally_output) -> bool` (e.g. in `memory/triggers.py` or `memory/manager.py`):

```python
def resolve_run_ended(observation: Any, ally_output: Any) -> bool:
    """Resolves whether a run has ended based on priority:
    1. Collector native signal (`observation.run_ended`) takes absolute priority.
    2. Ally semantic output (`ally_output.run_boundary == "run_ended"`) serves as fallback.
    """
    if getattr(observation, "run_ended", False):
        return True
    if getattr(ally_output, "run_boundary", "none") == "run_ended":
        return True
    return False
```

---

## 4. Database Table (`memory/db.py`)

Add `cross_session_memory` table to `MemoryDB._init_db()`:

```sql
CREATE TABLE IF NOT EXISTS cross_session_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT NOT NULL,
    game_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    save_id_closed TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

Add database methods on `MemoryDB`:

- `get_latest_cross_session(player_id: str, game_id: str) -> dict[str, Any] | None`
- `insert_cross_session(player_id: str, game_id: str, summary: str, save_id_closed: str) -> None`

---

## 5. `close_run()` Method on `NarrativeMemoryManager` and `MemorySystem`

### A. `NarrativeMemoryManager` (`memory/narrative.py`)

Add `close_run()`:

1. Ensure the current run has a long-term summary (if not, call `flush_to_long_term()` first).
2. Fetch the latest cross-session summary from `cross_session_memory` (if any, else note `"this is the first recorded run"`).
3. Invoke LLM with `CROSS_SESSION_SUMMARY_PROMPT`.
4. Insert the new synthesis into `cross_session_memory`.
5. Call `self.save_tracker.close(self.player_id, self.game_id, self.save_id)`.

### B. `MemorySystem` (`memory/manager.py`)

Delegate `close_run()` to `NarrativeMemoryManager`. Also update `flush_to_cross_session()` safety net to call `close_run()` if the session is still open.

---

## 6. Wiring in `main.py`

In the main turn loop:

1. After receiving `observation` and `ally_output`, call `resolve_run_ended(observation, ally_output)`.
2. If `True`, trigger `memory_system.close_run()`, log the run closure, and optionally start a new run session or handle gracefully.

---

## 7. Unit Tests Design

- **`memory/test_run_boundary.py`**:
  - Test `resolve_run_ended` with collector signal True + Ally none -> True.
  - Test collector signal False + Ally run_ended -> True.
  - Test both False -> False.
  - Test collector signal True takes priority even if Ally says run_ended.
- **`memory/test_cross_session.py`**:
  - Test `close_run()` writes exactly one `cross_session_memory` row.
  - Test `build_context()` surfaces the cross-session summary.
  - Test second run merges with prior cross-session entry (mocking LLM provider call and asserting prompt input).
