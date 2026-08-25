# Sub-Plan: Pass 1 Step 5 — Wire Trigger System & Decouple Buffer Size from Flush Cadence

This sub-plan covers the detailed specifications and implementation design for Pass 1 Step 5 of [`plans/ally_memory_and_speedup_implementation_plan.md`](plans/ally_memory_and_speedup_implementation_plan.md:255).

## Objectives

1. Implement `CompositeTrigger` in [`memory/triggers.py`](memory/triggers.py:1) to allow combining multiple trigger conditions (turn count, importance threshold, explicit checkpoints).
2. Update [`NarrativeMemoryManager.__init__`](memory/narrative.py:28) and [`MemorySystem.__init__`](memory/manager.py:16) to add `medium_flush_interval: int = 8` and use `CompositeTrigger` by default.
3. Ensure `importance` and `explicit_checkpoint` are correctly passed through the `context` dict in [`NarrativeMemoryManager.record_turn()`](memory/narrative.py:66).
4. Design robust unit tests in [`memory/test_triggers.py`](memory/test_triggers.py:1) (or equivalent test file) covering individual triggers, `CompositeTrigger`, and medium-term flush triggering behavior.

---

## Detailed Specifications

### 1. Addition of `CompositeTrigger` in [`memory/triggers.py`](memory/triggers.py:1)

Add [`CompositeTrigger`](memory/triggers.py:1) inheriting from [`Trigger`](memory/triggers.py:8):

```python
class CompositeTrigger(Trigger):
    def __init__(self, triggers: list[Trigger]):
        self.triggers = triggers

    def should_trigger(self, context: dict[str, Any]) -> bool:
        return any(t.should_trigger(context) for t in self.triggers)
```

### 2. Updates to `NarrativeMemoryManager` and `MemorySystem`

- **[`NarrativeMemoryManager.__init__`](memory/narrative.py:28)**:
  - Add parameter `medium_flush_interval: int = 8`.
  - Update default `flush_trigger` to:
    ```python
    self.flush_trigger = flush_trigger or CompositeTrigger([
        TurnCountTrigger(interval=medium_flush_interval),
        SalienceEventTrigger(importance_threshold=8),
        ExplicitAllyTrigger()
    ])
    ```
- **[`MemorySystem.__init__`](memory/manager.py:16)** (`memory/manager.py`):
  - Add parameter `medium_flush_interval: int = 8`.
  - Pass `medium_flush_interval=medium_flush_interval` down into [`NarrativeMemoryManager.__init__`](memory/narrative.py:28).

### 3. Context Passing in `record_turn()`

In [`NarrativeMemoryManager.record_turn()`](memory/narrative.py:66):
```python
context = {"turn": turn, "importance": importance, "explicit_checkpoint": explicit_checkpoint}
if self.flush_trigger.should_trigger(context):
    self._flush_to_medium_term()
```
This dictionary ensures that [`TurnCountTrigger`](memory/triggers.py:15), [`SalienceEventTrigger`](memory/triggers.py:28), and [`ExplicitAllyTrigger`](memory/triggers.py:37) all receive their required evaluation inputs (`turn`, `importance`, `explicit_checkpoint`).

---

## Unit Test Design

Create or extend unit tests (e.g., [`memory/test_triggers.py`](memory/test_triggers.py:1)) covering:
1. **Individual Triggers**:
   - [`TurnCountTrigger`](memory/triggers.py:15) triggers only on multiples of interval.
   - [`SalienceEventTrigger`](memory/triggers.py:28) triggers when `importance >= threshold`.
   - [`ExplicitAllyTrigger`](memory/triggers.py:37) triggers when `explicit_checkpoint == True`.
2. **`CompositeTrigger`**:
   - Returns `True` if any sub-trigger returns `True`, `False` otherwise.
3. **`NarrativeMemoryManager` Integration**:
   - Confirm that calling [`NarrativeMemoryManager.record_turn()`](memory/narrative.py:66) with `importance=9` triggers a medium-term flush even if turn count is not a multiple of `medium_flush_interval`.
   - Confirm explicit checkpoints trigger medium-term flush.
