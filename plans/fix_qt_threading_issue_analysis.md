# Fix for Qt Threading Issue: QTextDocument Cross-Thread Violation in Dev Inspector

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [The Error](#the-error)
3. [Root Cause Analysis](#root-cause-analysis)
4. [Affected Code Sections](#affected-code-sections)
5. [Architectural Context](#architectural-context)
6. [Fix Options](#fix-options)
7. [Compatibility Analysis](#compatibility-analysis)
8. [Recommended Path Forward](#recommended-path-forward)
9. [Implementation Plan](#implementation-plan)
10. [Testing Strategy](#testing-strategy)

---

## Executive Summary

The Ally application experiences a Qt threading error (`QObject: Cannot create children for a parent that is in a different thread`) that **only manifests when the dev inspector window is open**. This occurs because background threads (LLM processing, perception pipelines, collectors) emit log entries through the global logger, which directly invokes UI callback methods on those background threads. Qt enforces strict thread affinity: GUI objects like `QTextDocument` (used by `QTextEdit`) must be accessed only from the thread that created them (the main UI thread).

**Important clarification**: The `CoreBridge` class **already handles** Qt signal marshalling for most cross-thread scenarios. All `AllyCore` EventHooks (images, OCR results, scribe output, ally output, thinking streams, etc.) are already properly bridged to Qt signals in [`CoreBridge.set_core()`](interfaces/gui_qt/dev/bridge.py:44). Qt signals use `QueuedConnection` by default when crossing threads, so these callbacks automatically execute on the main Qt thread.

This document provides a comprehensive analysis of the problem, affected code, architectural implications, and recommends a **minimal, surgical fix** targeting only the remaining cross-thread violations (logger subscribers in dev panels) that maintains full backward compatibility with terminal/file logging while resolving the Qt thread-safety violation.

---

## The Error

### Error Message
```
QObject: Cannot create children for a parent that is in a different thread.
(Parent is QTextDocument(0x25021f62f80), parent's thread is QThread(0x24fdd5157d0), current thread is QThread(0x25022556900)
```

### When It Occurs
- **Only when the dev inspector window is open**
- During background thread operations (LLM reasoning, screen capture, perception processing)
- When those threads emit log messages via the global `log()` function
- **NOT affected**: Vision pipeline images, debug overlays, OCR results, Ally output, Scribe output, and thinking streams are already properly marshalled via `CoreBridge`

### Why It Happens
Qt's object hierarchy enforces that **all parent-child relationships must exist within the same thread**. When `QTextEdit.append()` or `QTextEdit.setPlainText()` is called from a background thread:
1. Qt needs to create/modify internal `QTextDocument` objects
2. These objects are children of the `QTextEdit` widget
3. The `QTextEdit` was created on the main UI thread
4. The modification attempt comes from a background thread
5. Qt's internal checking detects the thread mismatch and raises this warning

**Note**: This is a warning, not a crash, but it indicates undefined behavior and can lead to subtle bugs, visual artifacts, or actual crashes in Qt applications.

---

## Root Cause Analysis

### Call Chain

```
Background Thread (e.g., LLM reasoning, collector)
    ↓
log() function called (infrastructure/logger/logger.py:217)
    ↓
Logger iterates through _subscribers list (logger.py:295)
    ↓
Direct callback invocation: sub(entry) on background thread
    ↓
DevInspector Panels' _on_log_entry() methods executed on background thread
    ↓
QTextEdit.append() or setPlainText() called on background thread
    ↓
Qt detects cross-thread access to QTextDocument → ERROR
```

### The Core Problem
The global logger's `subscribe()` mechanism does **not** perform any thread marshalling. It directly invokes all registered callbacks on whatever thread calls `log()`. This is safe for terminal/file logging (which are thread-agnostic), but **unsafe for Qt GUI components**.n

### Existing Infrastructure
The codebase already has a solution for this pattern in [`utils/qt_safe_event_hook.py`](utils/qt_safe_event_hook.py:1):
- `QtSignalBridge`: Singleton QObject for signal emission
- `QtSafeCallbackWrapper`: Wraps callbacks for Qt-thread-safe invocation
- `QtSafeEventHook`: Wrapper for EventHook that dispatches to Qt main thread
- Uses `QMetaObject.invokeMethod()` with `Qt.QueuedConnection` for safe cross-thread invocation

---

## Affected Code Sections

### What's NOT Affected (Already Thread-Safe via CoreBridge)

**Important**: The [`CoreBridge`](interfaces/gui_qt/dev/bridge.py:8) class already properly bridges all `AllyCore` EventHooks to Qt Signals. The following are **NOT affected** by cross-thread issues:

- **Images**: `DebugPanel.handle_debug_overlay()` - connected via `core.on_debug_overlay` → `bridge.debug_overlay_ready` signal
- **Vision Pipeline Images**: `VisionPanel.handle_pipeline_image()` - connected via `core.on_pipeline_image` → `bridge.pipeline_image_ready` signal
- **OCR Results**: `OcrPanel.handle_ocr_result()` - connected via `core.on_ocr_result` → `bridge.ocr_result_ready` signal
- **Scribe Output**: `ScribePanel.handle_scribe_output()` - connected via `core.on_scribe_output` → `bridge.scribe_output_ready` signal
- **Ally Output**: `AllyPanel.handle_ally_output()` - connected via `core.on_ally_output` → `bridge.ally_output_ready` signal
- **Thinking Streams**: All thinking panel handlers - connected via corresponding `bridge.thinking_stream_*` signals

These Qt Signal connections use `QueuedConnection` by default when crossing thread boundaries, automatically marshalling the callbacks to the main Qt thread.

### What IS Affected (Logger Subscribers)

The **only** remaining cross-thread violations are from direct logger `subscribe()` calls:

### 1. Logger Core (The Emission Point)
**File**: [`infrastructure/logger/logger.py`](infrastructure/logger/logger.py:217)

**Relevant Code**:
```python
# Line 288-296
for sub in list(_subscribers):
    try:
        sub(entry)
    except Exception as e:
        log("Error in subscriber callback: {error}", error=str(e), level="error")
```

**Issue**: Direct synchronous callback invocation on the calling thread.

### 2. Dev Inspector Output Panel
**File**: [`interfaces/gui_qt/dev/panels/output_panel.py`](interfaces/gui_qt/dev/panels/output_panel.py:10)

**Relevant Code**:
```python
# Line 40
subscribe(self._on_log_entry)

# Line 42-48
def _on_log_entry(self, entry: LogEntry) -> None:
    self._all_entries.append(entry)
    if len(self._all_entries) > 1000:
        self._all_entries.pop(0)
    self._append_entry_if_matches(entry)

# Line 54-56
def _append_entry_if_matches(self, entry: LogEntry) -> None:
    channel = self._combo.currentText()
    if channel == "All" or entry.brain_name.lower() == channel.lower():
        line = f"[{entry.brain_name}] {entry.message}"
        self._text.append(line)  # ← QTextEdit modification on background thread
```

**Issue**: `self._text.append()` called directly from background thread via logger callback.

### 3. Dev Inspector Vision Panel
**File**: [`interfaces/gui_qt/dev/panels/vision_panel.py`](interfaces/gui_qt/dev/panels/vision_panel.py:17)

**Relevant Code**:
```python
# Line 65
subscribe(self._on_log_entry)

# Line 116-125
def _on_log_entry(self, entry: LogEntry) -> None:
    """Receives log entries and filters for vision/OCR channels."""
    if entry.brain_name.lower() not in ("vision", "ocr", "classifier"):
        return
    self._log_tail.append(f"[{entry.brain_name}] {entry.message}")
    if len(self._log_tail) > 5:
        self._log_tail.pop(0)
    self._log_text.setPlainText("\n".join(self._log_tail))  # ← QTextEdit modification on background thread
```

**Issue**: `self._log_text.setPlainText()` called directly from background thread.

### 4. Dev Inspector Memory Panel
**File**: [`interfaces/gui_qt/dev/panels/memory_panel.py`](interfaces/gui_qt/dev/panels/memory_panel.py:6)

**Relevant Code**:
```python
# Line 42
subscribe(self._on_log_entry)

# Line 65-74
def _on_log_entry(self, entry: LogEntry) -> None:
    """Receives log entries filtered for memory/save channels."""
    if entry.brain_name.lower() not in ("memory", "save"):
        return
    self._log_tail.append(f"[{entry.brain_name}] {entry.message}")
    if len(self._log_tail) > 5:
        self._log_tail.pop(0)
    self._log_text.setPlainText("\n".join(self._log_tail))  # ← QTextEdit modification on background thread
```

**Issue**: `self._log_text.setPlainText()` called directly from background thread.

### 4. Dev Inspector Vision Panel
**File**: [`interfaces/gui_qt/dev/panels/vision_panel.py`](interfaces/gui_qt/dev/panels/vision_panel.py:17)

**Relevant Code**:
```python
# Line 65
subscribe(self._on_log_entry)

# Line 116-125
def _on_log_entry(self, entry: LogEntry) -> None:
    """Receives log entries and filters for vision/OCR channels."""
    vision_brains = {"ScreenClassifier", "ScreenBootstrapper", "LayoutOCRReader", "OCR", "ClipClassifier", "CategoryStore"}
    if entry.brain_name in vision_brains or "vision" in entry.method_name.lower():
        line = f"[{entry.brain_name}] {entry.message}"
        self._log_tail.append(line)
        if len(self._log_tail) > 5:
            self._log_tail.pop(0)
        self._log_text.setPlainText("\n".join(self._log_tail))  # ← QTextEdit modification on background thread
```

**Issue**: `self._log_text.setPlainText()` called directly from background thread via logger callback.

### 5. Dev Inspector Memory Panel
**File**: [`interfaces/gui_qt/dev/panels/memory_panel.py`](interfaces/gui_qt/dev/panels/memory_panel.py:6)

**Relevant Code**:
```python
# Line 42
subscribe(self._on_log_entry)

# Line 65-74
def _on_log_entry(self, entry: LogEntry) -> None:
    """Receives log entries filtered for memory/save channels."""
    if entry.brain_name.lower() not in ("memory", "save"):
        return
    self._log_tail.append(f"[{entry.brain_name}] {entry.message}")
    if len(self._log_tail) > 5:
        self._log_tail.pop(0)
    self._log_text.setPlainText("\n".join(self._log_tail))  # ← QTextEdit modification on background thread
```

**Issue**: `self._log_text.setPlainText()` called directly from background thread via logger callback.

### 6. Other Potential Subscribers
**File**: [`interfaces/visuals/header.py`](interfaces/visuals/header.py:133) (line 135)

**Relevant Code**:
```python
try:
    from infrastructure.logger import subscribe, unsubscribe
    subscribe(on_log)
except Exception:
    pass
```

**Status**: This appears to be a legacy Tkinter component (deprecated per user confirmation). No action needed for Qt compatibility.

---

## Architectural Context

### Thread Model

```
┌─────────────────────────────────────────────────────────────┐
│                        MAIN THREAD (Qt GUI)                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  ProdOverlay     │  │  DevInspector    │  │  StatusStrip │ │
│  │  Window          │  │  Window          │  │              │ │
│  └────────┬────────┘  └────────┬────────┘  └──────┬──────┘ │
│           │                    │                    │          │
└───────────┼────────────────────┼────────────────────┼──────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌───────────────────────────────────────────────────────────────┐
│                     BACKGROUND THREADS                           │
│                                                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │  AllyCore        │  │  Collector       │  │  Voice        │ │
│  │  run_loop()      │  │  Screen Capture  │  │  Input        │ │
│  │                 │  │                 │  │  Controller   │ │
│  └────────┬────────┘  └────────┬────────┘  └───────┬───────┘ │
│           │                    │                     │          │
│           ▼                    ▼                     ▼          │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    log() → _subscribers[]                    │ │
│  │               (DIRECT CALLBACK INVOCATION)                  │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

### Data Flow
1. **Background threads** perform work (LLM, perception, etc.)
2. **For EventHooks**: `AllyCore` emits events, `CoreBridge` catches them and re-emits via Qt Signals (thread-safe by default)
3. **For Logging**: They call `log()` to emit status/debug information
4. Logger iterates `_subscribers` and calls each callback **synchronously on the background thread**
5. Dev inspector panel callbacks receive the log entry and update their `QTextEdit` widgets
6. **Qt detects cross-thread access** because `QTextEdit` belongs to the main thread

### Why Most Things Already Work via CoreBridge

The [`CoreBridge`](interfaces/gui_qt/dev/bridge.py:8) class in [`dev_window.py`](interfaces/gui_qt/dev/dev_window.py:76) (lines 76-85) already connects most `AllyCore` EventHooks to Qt Signals:

```python
# CoreBridge.set_core() does this for many hooks:
core.on_pipeline_image.connect(lambda k, img, t: self.pipeline_image_ready.emit(k, img, t or ""))
core.on_debug_overlay.connect(lambda img: self.debug_overlay_ready.emit(img))
core.on_ocr_result.connect(lambda payload: self.ocr_result_ready.emit(payload))
# ... etc for scribe, ally output, thinking streams
```

Since these are Qt Signal connections, and Qt automatically uses `QueuedConnection` for cross-thread signal-slot connections, all these handlers execute on the main Qt thread regardless of which thread emitted the original `AllyCore` EventHook.

**The logger is the only remaining issue** because it uses direct Python callback invocation rather than Qt signals.

### Existing Thread-Safe Patterns
The codebase already implements two thread-safety mechanisms:

1. **`EventHook`** (`utils/event_hook.py`):
   - Thread-safe subscriber list management via `_subscriber_lock` (RLock)
   - Emits to a snapshot of subscribers to avoid iteration issues
   - **But**: Callbacks are still invoked on the calling thread

2. **`QtSafeEventHook`** (`utils/qt_safe_event_hook.py`):
   - Wraps `EventHook` to marshal callbacks to Qt main thread
   - Uses `QMetaObject.invokeMethod()` with `Qt.QueuedConnection`
   - **Pattern**: Callbacks are wrapped, and their `emit()` method is connected to the original hook
   - The wrapper's `emit()` uses Qt's mechanism to queue the call on the main thread

---

## Fix Options

### Option 1: Make All Logger Subscribers Qt-Safe (Recommended)

**Approach**: Modify the logger to automatically marshal callbacks to the Qt main thread when a Qt application context is detected.

**Pros**:
- Centralized fix in one location
- All existing and future subscribers benefit automatically
- No changes needed to individual panel code
- Maintains backward compatibility with terminal/file logging

**Cons**:
- Slight overhead for all logger calls (Qt context detection)
- Requires detection of Qt application context
- More complex logger implementation

**Implementation**:
- Modify `subscribe()` to wrap callbacks in `QtSafeCallbackWrapper` when Qt is available
- Modify `_subscribers` iteration to check if each callback needs Qt marshalling
- Fall back to direct invocation for non-Qt contexts

### Option 2: Create Qt-Specific Logger Subscribers

**Approach**: Modify the dev inspector panels to use Qt-safe versions of their log handlers.

**Pros**:
- Minimal changes to logger core
- Explicit about which subscribers need Qt safety
- Clear separation of concerns
- Easy to understand and maintain

**Cons**:
- Requires changes to each dev panel
- Future Qt subscribers must remember to use the safe pattern
- More files to modify

**Implementation**:
- Create `QtSafeLogSubscriber` class that wraps log callbacks
- Modify each dev panel to use this wrapper
- Remove direct `subscribe()` calls from panels

### Option 3: Dual-Path Logger Emission

**Approach**: Have the logger detect if it's being called from a non-Qt thread and use `QMetaObject.invokeMethod` to marshal all callbacks when needed.

**Pros**:
- Completely transparent to subscribers
- Single point of change
- Optimal performance (only marshal when needed)

**Cons**:
- Most complex implementation
- Requires careful handling of Qt application state
- Potential for subtle bugs if Qt context changes

**Implementation**:
- Add `QApplication.instance()` check to detect Qt context
- Track the main thread ID
- When called from non-main thread, marshal all callbacks via Qt mechanism

### Option 4: Use Signals for All Logger Emission (Most Invasive)

**Approach**: Restructure the logger to emit all log entries as Qt signals, with subscribers connecting to those signals.

**Pros**:
- Most Qt-idiomatic approach
- Guaranteed thread safety for all Qt components
- Clean separation between logging and Qt event systems

**Cons**:
- Major architectural change
- Requires Qt to be available even for non-GUI use
- Complex for terminal/file logging
- Breaking change for all logger users

**Implementation**:
- Create `LoggerQObject` that emits log signals
- Modify `log()` to emit via this object
- Convert all subscribers to Qt signal/slot connections

---

## Compatibility Analysis

### Terminal Logging
**Impact**: None. Terminal logging uses `print()` and file I/O, which are thread-safe and do not depend on Qt. All options preserve the existing terminal output behavior.

### File Logging
**Impact**: None. File logging writes to disk, which is thread-safe (assuming proper file handle management, which the current implementation already handles).

### Existing Non-Qt Subscribers
**Impact**: None for Options 1-3. The logger will continue to work exactly as before for non-Qt contexts, with callbacks invoked directly. Option 4 would require all subscribers to connect via Qt signals, which is a breaking change.

### Performance
**Impact**: Minimal. Options 1-3 add at most one level of indirection (QueuedConnection) which involves posting an event to the Qt event loop. This is already the pattern used by `QtSafeEventHook` for other cross-thread scenarios and has proven negligible impact.

### Tkinter GUI (Deprecated)
**Impact**: None per user confirmation. The Tkinter GUI is deprecated and does not need to be considered for compatibility.

---

## Recommended Path Forward

### Recommendation: **Option 2 - Create Qt-Specific Logger Subscribers**

This approach provides the best balance of safety, simplicity, and maintainability:

1. **Surgical Fix**: Only modify the affected dev inspector panels
2. **Explicit**: Makes it clear which subscribers need Qt thread safety
3. **Non-Invasive**: No changes to the core logger, preserving all existing functionality
4. **Extensible**: Provides a clear pattern for future Qt subscribers
5. **Proven Pattern**: Uses the already-existing `QtSignalBridge` infrastructure

### Why Not Option 1?
While Option 1 (centralized fix) is appealing, it has several drawbacks:
- Adds complexity to the logger core
- Requires Qt context detection logic
- Makes the logger implicitly aware of UI concerns (separation of concerns violation)
- More difficult to test and maintain

### Why Not Option 3?
Option 3 (dual-path emission) shares the complexity issues of Option 1 and adds potential for subtle bugs related to Qt context detection.

### Why Not Option 4?
Option 4 (signals for all emission) is architecturally cleaner in a pure Qt world, but would be a massive breaking change and violates the separation between logging infrastructure and GUI framework.

---

## Implementation Plan

### Phase 1: Create Qt-Safe Log Subscriber Infrastructure

**File**: `interfaces/gui_qt/dev/qt_safe_logger.py` (new)

```python
"""Qt-safe logger subscriber infrastructure for dev inspector panels.

This module provides a thread-safe way for Qt GUI components to receive
log entries from background threads without violating Qt's thread affinity rules.
"""

from typing import Callable, Any, Optional
from PySide6.QtCore import QObject, Signal, Slot, QMetaObject, Qt
from infrastructure.logger.logger import LogEntry, subscribe, unsubscribe


class QtLogEntryBridge(QObject):
    """QObject that emits LogEntry objects for Qt-safe delivery."""
    
    log_entry_received = Signal(object)  # Emits LogEntry
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)


# Singleton bridge instance
_qt_log_bridge: Optional[QtLogEntryBridge] = None


def get_qt_log_bridge() -> QtLogEntryBridge:
    """Get or create the singleton QtLogEntryBridge."""
    global _qt_log_bridge
    if _qt_log_bridge is None:
        _qt_log_bridge = QtLogEntryBridge()
    return _qt_log_bridge


class QtSafeLogSubscriber(QObject):
    """A subscriber that receives log entries on the Qt main thread.
    
    Connect this to a callback that updates Qt widgets. The callback
    will be invoked on the main Qt thread regardless of which thread
    emitted the log entry.
    """
    
    def __init__(
        self,
        callback: Callable[[LogEntry], None],
        parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self._callback = callback
        self._bridge = get_qt_log_bridge()
        self._bridge.log_entry_received.connect(self._handle_entry)
        
        # Subscribe to the global logger
        subscribe(self._forward_to_qt)
    
    def _forward_to_qt(self, entry: LogEntry) -> None:
        """Forward log entry to Qt main thread via signal."""
        # This will invoke _handle_entry on the Qt main thread
        self._bridge.log_entry_received.emit(entry)
    
    @Slot(object)
    def _handle_entry(self, entry: LogEntry) -> None:
        """Handle log entry on Qt main thread."""
        try:
            self._callback(entry)
        except Exception as e:
            from infrastructure.logger.logger import log
            log("Error in Qt-safe log callback: {error}", error=str(e), level="error")
    
    def unsubscribe(self) -> None:
        """Unsubscribe from the global logger."""
        unsubscribe(self._forward_to_qt)
        self._bridge.log_entry_received.disconnect(self._handle_entry)
```

### Phase 2: Update Dev Inspector Panels

#### OutputPanel (`interfaces/gui_qt/dev/panels/output_panel.py`)

**Changes**:
1. Remove direct `subscribe(self._on_log_entry)` from `__init__`
2. Add `QtSafeLogSubscriber` for Qt-safe log reception
3. Store reference to subscriber for cleanup

```python
# In __init__:
from interfaces.gui_qt.dev.qt_safe_logger import QtSafeLogSubscriber

# Remove: subscribe(self._on_log_entry)

# Add:
self._qt_log_subscriber = QtSafeLogSubscriber(self._on_log_entry, self)

# In closeEvent:
def closeEvent(self, event: Any) -> None:
    self._qt_log_subscriber.unsubscribe()
    super().closeEvent(event)
```

#### VisionPanel (`interfaces/gui_qt/dev/panels/vision_panel.py`)

Same pattern as OutputPanel:
1. Replace `subscribe(self._on_log_entry)` with `QtSafeLogSubscriber`
2. Properly unsubscribe in `closeEvent`

#### MemoryPanel (`interfaces/gui_qt/dev/panels/memory_panel.py`)

Same pattern as OutputPanel and VisionPanel.

### Phase 3: Testing & Validation

Run the application with:
1. Dev inspector window open
2. Background operations active (LLM, perception, etc.)
3. Verify no threading errors appear
4. Verify all log entries display correctly in all panels
5. Verify terminal/file logging continues to work normally

---

## Testing Strategy

### Unit Tests
1. **QtSafeLogSubscriber Test**: Verify that callbacks are invoked on the correct thread
2. **Thread Affinity Test**: Verify that QTextEdit operations only happen on the main thread
3. **Logger Compatibility Test**: Verify that terminal/file logging still works

### Integration Tests
1. **Dev Inspector Smoketest**: Open dev window, trigger background operations, verify no errors
2. **Multi-Panel Test**: Verify all panels (Output, Vision, Memory) receive and display logs correctly
3. **Stress Test**: Rapid logging from multiple background threads

### Regression Tests
1. **Terminal Logging**: Run in headless mode, verify terminal output
2. **File Logging**: Verify log files are written correctly
3. **Existing Tests**: Ensure all existing unit tests continue to pass

---

## Files to Modify

### New Files
- `interfaces/gui_qt/dev/qt_safe_logger.py` (Qt-safe logger subscriber infrastructure)

### Modified Files
- `interfaces/gui_qt/dev/panels/output_panel.py` (Qt-safe subscription for logger)
- `interfaces/gui_qt/dev/panels/vision_panel.py` (Qt-safe subscription for logger)
- `interfaces/gui_qt/dev/panels/memory_panel.py` (Qt-safe subscription for logger)

### No Changes Required
- `infrastructure/logger/logger.py` (core logger unchanged)
- `main.py` (no changes needed)
- `brain/reasoning/core.py` (no changes needed)
- `interfaces/gui_qt/dev/bridge.py` (already handles all EventHooks correctly via Qt Signals)
- `interfaces/gui_qt/dev/panels/debug_panel.py` (already thread-safe via CoreBridge)
- `interfaces/gui_qt/dev/panels/ocr_panel.py` (already thread-safe via CoreBridge)
- `interfaces/gui_qt/dev/panels/scribe_panel.py` (already thread-safe via CoreBridge)
- `interfaces/gui_qt/dev/panels/ally_panel.py` (already thread-safe via CoreBridge)
- `interfaces/gui_qt/dev/panels/thinking_panel.py` (already thread-safe via CoreBridge)
- All other files (no impact)

---

## Expected Outcome

After implementing this fix:

1. **The threading error will be eliminated** when the dev inspector window is open
2. **All log entries will display correctly** in all dev inspector panels (Output, Vision, Memory)
3. **Terminal and file logging will continue to work exactly as before**
4. **No performance impact** on logging or application operations
5. **Clear pattern established** for future Qt subscribers that need thread safety
6. **All other dev inspector panels** (Debug, OCR, Scribe, Ally, Thinking, Entity, Timing) **already work correctly** due to existing CoreBridge thread marshalling

---

## Summary

**The issue**: The dev inspector window triggers Qt cross-thread errors because logger subscribers update `QTextEdit` widgets from background threads.

**The clarification**: The [`CoreBridge`](interfaces/gui_qt/dev/bridge.py:8) class **already handles** Qt signal marshalling for all `AllyCore` EventHooks. This means:

- ✅ **Already thread-safe**: Vision pipeline images, debug overlays, OCR results, Scribe output, Ally output, Thinking streams, Entity data, Memory polling
- ❌ **Needs fixing**: Logger subscribers in OutputPanel, VisionPanel, MemoryPanel

**The fix**: Only the three panels that directly subscribe to the logger need to use Qt-safe logger subscribers. All other dev inspector functionality already works correctly via the existing CoreBridge infrastructure.

## Appendix: Qt Thread Safety Reference

### Qt Thread Affinity Rules
- Every `QObject` (including all widgets) has a thread affinity
- A `QObject` can only be accessed from its affiliated thread
- Child objects automatically inherit the parent's thread affinity
- `QTextEdit` creates a `QTextDocument` child object internally
- Any modification to a `QTextEdit` or its document must happen on the main thread

### Proper Cross-Thread Communication
The correct way to update Qt GUI from a background thread:

```python
# From background thread:
QMetaObject.invokeMethod(
    target_object,           # QObject in main thread
    "method_name",           # Slot to call
    Qt.QueuedConnection,     # Connection type
    arg1, arg2, ...          # Arguments
)
```

This posts an event to the main thread's event loop, which then invokes the specified slot on the main thread when the loop processes the event.

### Connection Types
- `Qt.AutoConnection` (default): Qt chooses based on thread affinity
- `Qt.DirectConnection`: Invokes immediately on current thread (dangerous!)
- `Qt.QueuedConnection`: Posts event to receiver's thread (what we need)
- `Qt.BlockingQueuedConnection`: Like Queued but waits for completion

For GUI updates from background threads, **`Qt.QueuedConnection`** is always the correct choice.
