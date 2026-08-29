# Phase 1: Logger Timing Implementation Plan

## Overview
Implementing a timing decorator for the logger that will measure function execution time and display it in log output.

---

## Current vs Suggested Code Analysis

### Key Differences

| Feature | Current Code | Suggested Code | Impact |
|---------|--------------|---------------|--------|
| Return type of `resolve_module_info` | `tuple[str, str, str]` (3 values) | `tuple[str, str, str, float \| None]` (4 values) | **Breaking change** - all callers must handle 4th return value |
| Thread safety for timing | N/A | Thread-local storage via `_timing_storage` | Adds thread safety |
| Timing decorator | N/A | New `@timed` decorator | New functionality |
| Elapsed time in log output | Not displayed | ` +0.00123s` appended to method name | New visual feature |
| `log()` function signature | Unchanged | Unchanged | No breaking change |
| Pub/Sub subsystem | Kept | Removed in suggested code | **Breaking change** - subscribers won't receive entries |

### Critical Side-Effect Concerns

#### 1. Subscriber System Removal
**Issue**: The suggested code removes the entire pub/sub system (`subscribe`, `unsubscribe`, `_subscribers`, `LogEntry` dispatch in `log()`).

**Current code locations using pub/sub**:
- `tests/test_logger_pubsub.py` - Tests rely on `subscribe`/`unsubscribe`

**Mitigation**: The subscriber code will be kept in Phase 1 to avoid breaking existing functionality.

#### 2. Return Type Change in `resolve_module_info`
**Issue**: Changing from 3 to 4 return values is a breaking change for any code that unpacks the result.

**Current code locations**:
- `log()` function (line 181) - needs update to unpack 4 values

**Mitigation**: Update `log()` to unpack 4 values, ignoring the 4th if not used.

#### 3. `_strip_ansi` Function
**Issue**: The suggested code moves `import re` inside the function. Current code has it at module level.

**Mitigation**: Keep `import re` at module level for consistency.

#### 4. File Logging Removal
**Issue**: The suggested code completely removes file logging logic (lines 229-237 in current code).

**Mitigation**: Keep file logging functionality.

---

## Implementation Plan

### Changes to `infrastructure/logger/logger.py`

1. **Add imports** (if not present):
   - `import threading`
   - `import time`

2. **Add timing storage** (after `_strip_ansi`):
   ```python
   _timing_storage = threading.local()
   
   def _get_timing_stack() -> dict:
       if not hasattr(_timing_storage, 'stack'):
           _timing_storage.stack = {}
       return _timing_storage.stack
   ```

3. **Add `@timed` decorator**:
   ```python
   def timed(func: Callable) -> Callable:
       """Decorator to track function execution time seamlessly with the tree logger."""
       from functools import wraps
       @wraps(func)
       def wrapper(*args, **kwargs):
           stack = _get_timing_stack()
           code_obj = func.__code__
           if code_obj not in stack:
               stack[code_obj] = []
           stack[code_obj].append(time.perf_counter())
           try:
               return func(*args, **kwargs)
           finally:
               if code_obj in stack and stack[code_obj]:
                   stack[code_obj].pop()
                   if not stack[code_obj]:
                       del stack[code_obj]
       return wrapper
   ```

4. **Update `resolve_module_info` return type and implementation**:
   - Change return annotation to `tuple[str, str, str, float | None]`
   - Add elapsed time calculation in the frame traversal loop
   - Calculate elapsed: `time.perf_counter() - stack_timings[frame.f_code][-1]`

5. **Update `log()` function**:
   - Update unpacking: `brain_name, color_key, method_name, elapsed = resolve_module_info(name)`
   - Add timing display: `time_str = f" +{elapsed:.5f}s" if elapsed is not None else ""`
   - Include `time_str` in both `raw_prefix` and `terminal_prefix`

6. **Preserve existing functionality**:
   - Keep subscriber system (`subscribe`, `unsubscribe`, `_subscribers`, `LogEntry`)
   - Keep file logging logic
   - Keep `import re` at module level
   - Keep `Logger` class and `get_logger` function

---

## Export Updates

### `infrastructure/logger/__init__.py`

Add the `timed` decorator to exports:
```python
from infrastructure.logger.logger import log, get_logger, Logger, pretty_format, timed

__all__ = ["log", "get_logger", "Logger", "pretty_format", "timed"]
```

---

## Visual Output Example

**Before:**
```
[Ally][process_turn] Processing turn 42
```

**After (with @timed decorator on `process_turn`):**
```
[Ally][process_turn +0.00123s] Processing turn 42
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `infrastructure/logger/logger.py` | Add timing infrastructure, update functions |
| `infrastructure/logger/__init__.py` | Export `timed` decorator |

---

## Testing Considerations

After implementation:
1. Run existing tests: `python -m pytest tests/test_logger_pubsub.py -v`
2. Verify colored output still displays correctly
3. Test with `@timed` decorator on a sample function to see timing display

---

## Next Steps (Phase 2 - Not in this scope)

Phase 2 will involve adding `@timed` decorator to individual log methods across the codebase. This plan only covers Phase 1 (updating the logger.py file itself).
