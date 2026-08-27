# Non-Invasive Python Profiling and Diagnostic Tools Evaluation

This document evaluates non-invasive Python profiling and diagnostic tools designed to pinpoint long code hangs, deadlocks, or infinite loops in a running desktop/Python application **without requiring any modifications to the core codebase**.

---

## Overview Matrix

| Tool | Type | Code Modification Required? | Best Used For | Overhead | Platform Support |
| :--- | :--- | :--- | :--- | :--- | :--- |
| [`py-spy`](#1-py-spy) | Out-of-process sampling profiler | No | Live production/desktop hangs, flame graphs, identifying bottleneck functions | Extremely low | Linux, macOS, Windows (Administrator privileges recommended) |
| [`faulthandler`](#2-faulthandler) | Standard library signal handler | No (can be enabled via environment variable) | Deadlocks, GIL contention, sudden freezing, stack dumps on command/timeout | Negligible | Cross-platform |
| [`VizTracer`](#3-viztracer) | In-process/Out-of-process tracer | No (can attach to a running PID) | Detailed call trees, timing visualization, timeline HTML reports | Moderate to High | Cross-platform |
| [`gdb` / `lldb` / Process Tools](#4-native-debugger--os-level-diagnostics) | OS-level native debugger | No | C-extension deadlocks, blocking system calls, GIL lockups | None (when detached) | OS-dependent |

---

## Detailed Tool Analysis

### 1. `py-spy`

`py-spy` is a sampling profiler for Python programs written in Rust. Because it reads the Python process's memory from the outside using OS APIs (e.g., `ptrace` on Linux, Debug API on Windows), it does not need to modify the target Python code or even be imported within the script.

#### Pros
- **Zero code changes**: Attaches to any running Python process ID (`PID`).
- **Extremely low overhead**: Sampling-based (`--rate`), meaning it only inspects the process periodically without injecting instrumentation bytecode.
- **Rich visual outputs**: Can generate top-like live views (`top`), flat profiles, and interactive flame graphs (`record -o profile.svg`).
- **Works on frozen/hung processes**: Even if a thread is completely locked or hung in a heavy loop, `py-spy` can read its stack trace.

#### Cons
- **Platform/Permission restrictions**: On modern Linux distributions (due to `yama` security kernel settings) or Windows, running it may require elevated privileges (sudo/Administrator).
- **C-extension limitations**: Standard Python frames are fully visible, but native C/C++ extensions may show up as generic native frames unless debug symbols are present.

#### Usage Instructions

1. **Install `py-spy`**:
   ```bash
   pip install py-spy
   ```

2. **Live top view of a hung application**:
   ```bash
   py-spy top --pid <PID>
   ```

3. **Record a flame graph of a hanging process over 30 seconds**:
   ```bash
   py-spy record --pid <PID> --duration 30 --output hang_flamegraph.svg
   ```

4. **Launch a script directly under profiling**:
   ```bash
   py-spy record -- python main.py
   ```

---

### 2. `faulthandler`

`faulthandler` is built directly into Python's standard library (`import faulthandler`). While normally used inside code, it can be enabled externally via environment variables or signal triggers without changing application source code.

#### Pros
- **Zero external dependencies**: Part of the Python standard library.
- **Built-in deadlock and crash resilience**: Dumps Python traceback on segmentation faults, fatal errors, user signals, or timeouts.
- **Environment variable activation**: Can be enabled at startup via `PYTHONFAULTHANDLER=1` without editing code files.

#### Cons
- **Stack trace only**: Does not provide CPU profiling percentages, time breakdowns, or flame graphs—only the instantaneous stack trace of all threads.
- **Signal limitations on Windows**: Signal-based dumping (`SIGUSR1`) has differences on Windows compared to POSIX systems (though timeout-based dumping works well).

#### Usage Instructions

1. **Enable via Environment Variable at Startup**:
   ```bash
   # Linux / macOS
   PYTHONFAULTHANDLER=1 python main.py

   # Windows PowerShell
   $env:PYTHONFAULTHANDLER="1"; python main.py
   ```

2. **Dump traceback on timeout (e.g., if a routine hangs for more than 10 seconds)**:
   ```bash
   PYTHONFAULTHANDLER=1 PYTHONFAULTHANDLER_TIMEOUT=10 python main.py
   ```

3. **Dump stack traces on demand using SIGUSR1 (Linux/macOS)**:
   ```bash
   # Send signal to running PID
   kill -USR1 <PID>
   ```

---

### 3. `VizTracer`

`VizTracer` is a low-overhead tracing and profiling tool that can trace function entries/exits, arguments, and return values, and can attach to running processes.

#### Pros
- **Interactive HTML Timelines**: Generates rich, Chrome-tracing-compatible timeline views (`vizviewer`) where you can visually inspect execution flow, thread states, and time spent.
- **Process Attachment**: Can attach to an already running Python process (`--pid`).
- **Comprehensive Logging**: Captures not just CPU time, but also logging, sub-processes, and custom events.

#### Cons
- **Higher overhead**: Full tracing records every function call, which can noticeably slow down the application if left running continuously.
- **File size**: Long capture sessions can result in very large trace result JSON files.

#### Usage Instructions

1. **Install `VizTracer`**:
   ```bash
   pip install viztracer
   ```

2. **Attach to a running hanging process**:
   ```bash
   viztracer --pid <PID> --output_file result.json
   ```

3. **View the resulting trace graphically**:
   ```bash
   vizviewer result.json
   ```

---

### 4. Native Debugger & OS-Level Diagnostics (`gdb`, `lldb`, Process Monitor)

When a Python desktop application hangs inside a native C-extension (such as PyQt/Tkinter rendering loops, database drivers, or graphics libraries), Python-only sampling profilers might only show that the interpreter is waiting in a C call. OS-level tools help inspect the native stack.

#### Pros
- **Deep C/C++ stack inspection**: Reveals deadlocks in native threads, GUI message pumps, or driver locks.
- **No Python code modification required**.

#### Cons
- Harder to interpret for pure Python developers (requires symbol tables and familiarity with C stack frames).

#### Usage Instructions (`gdb` on Linux)

1. Attach `gdb` to the Python process:
   ```bash
   gdb -p <PID>
   ```
2. Print Python stack traces from within `gdb` (if Python debug symbols are installed):
   ```gdb
   (gdb) py-bt
   ```
3. Or view the native C/C++ stack:
   ```gdb
   (gdb) bt
   ```

---

## Recommended Diagnostic Workflow for Code Hangs

1. **Step 1: Immediate Triage with `faulthandler`**
   - Run the application with `PYTHONFAULTHANDLER=1` enabled. If the app freezes, inspect the stderr output or configure a timeout dump.

2. **Step 2: Pinpoint Bottlenecks with `py-spy`**
   - Once the application hangs, identify its process ID (`PID`) and run:
     [`py-spy top --pid <PID>`](#1-py-spy)
   - If a specific function is stuck in a loop or blocking call, `py-spy` will immediately highlight the exact line and function name.
   - Generate an SVG flame graph using [`py-spy record`](#1-py-spy) for offline analysis.

3. **Step 3: Deep Timeline Analysis with `VizTracer`**
   - If the hang is sporadic or involves asynchronous thread interaction, attach `VizTracer` via PID to inspect the precise execution timeline.
