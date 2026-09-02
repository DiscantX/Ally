# Ally Codebase Audit Plan

## Overview

This document outlines a comprehensive audit plan for the Ally codebase, which contains 189 Python files. The audit is organized into multiple phases, each addressing specific aspects of code quality, architecture, performance, and maintainability.

**Status**: In Progress  
**Last Updated**: 2026  
**Owner**: Mistral AI (Vibe Code)

---

## 📊 Phase 0: Discovery & Inventory (COMPLETED)

### Objective
Establish a complete understanding of the codebase structure, dependencies, and current state.

### Tasks
- [x] Inventory all 189 Python files
- [x] Map module dependencies and import graph
- [x] Identify core architectural components
- [x] Document thread boundaries and interaction patterns
- [x] Identify external dependencies (cv2, PIL, PySide6, SQLite, Google Gemini API)

### Deliverables
- [x] Complete file inventory
- [x] Architecture diagram (conceptual)
- [x] Thread interaction map
- [x] Dependency graph

---

## 🏗️ Phase 1: Architectural Review

### Objective
Evaluate the overall architecture for consistency, maintainability, and alignment with project goals.

### Focus Areas
- Pipeline architecture (Collectors → Scribe → State Sandbox → Entity Registry → Memory Manager → Ally → Output)
- Air-gap design (Scribe sees screenshots, Ally only sees extracted facts)
- Event-driven patterns (EventHook usage)
- Thread isolation (background threads for LLM, screen capture, voice input)
- Qt integration patterns

### Tasks
- [ ] Review module boundaries and responsibilities
- [ ] Evaluate separation of concerns
- [ ] Identify architectural anti-patterns
- [ ] Review Qt/PySide6 integration approach
- [ ] Assess plugin/extension architecture
- [ ] Document architectural decisions and rationale

### Deliverables
- [ ] Architecture review report
- [ ] List of architectural improvements
- [ ] Updated architecture documentation

---

## 🎨 Phase 2: Code Quality & Style

### Objective
Improve code readability, maintainability, and consistency across the codebase.

### Focus Areas
- Code style consistency (PEP 8 compliance)
- Type hints completeness and correctness
- Docstring quality and coverage
- Naming conventions
- Code organization and structure
- Unused imports and dead code

### Tasks
- [ ] Run static analysis (pylint, flake8, or ruff)
- [ ] Check type hints coverage with mypy
- [ ] Review docstring completeness
- [ ] Identify and remove dead code
- [ ] Standardize naming conventions
- [ ] Improve code organization

### Deliverables
- [ ] Code style guide for the project
- [ ] Static analysis report
- [ ] List of code quality improvements
- [ ] Linting configuration (if not present)

---

## ⚡ Phase 3: Performance Optimization

### Objective
Identify and address performance bottlenecks, particularly in the critical path.

### Focus Areas
- Screen capture and processing pipeline
- Computer vision operations (CLIP, OCR)
- Database operations (SQLite)
- LLM inference and response handling
- Memory usage patterns
- I/O operations

### Tasks
- [ ] Profile critical paths (screen capture → Ally response)
- [ ] Identify CPU-bound operations
- [ ] Review database query efficiency
- [ ] Evaluate caching strategies
- [ ] Assess memory usage patterns
- [ ] Identify blocking operations

### Deliverables
- [ ] Performance profiling report
- [ ] List of performance bottlenecks
- [ ] Performance optimization recommendations

---

## 🔒 Phase 4: Concurrency & Thread Safety (IN PROGRESS - HIGH PRIORITY)

### Objective
Ensure thread-safe operations throughout the codebase, particularly at thread boundaries.

### Focus Areas
- Thread interaction patterns
- Locking strategies and discipline
- Race conditions
- Deadlock prevention
- Qt thread safety (GUI updates from background threads)
- SQLite thread safety

### Critical Findings & Fixes

#### ✅ Completed Fixes
- [x] **Fix #1**: StateSandbox Thread Safety - Added RLock, wrapped update() and as_context()
- [x] **Fix #2**: AllyCore Locking Discipline - Changed state_lock to RLock, added _initialization_lock
- [x] **Fix #3**: EventHook Thread Safety - Added global _subscriber_lock, thread-safe connect/disconnect/emit
- [x] **Fix #4**: MemoryDB Thread Safety - Rewrote with RLock, check_same_thread=False, all DB methods locked
- [x] **Fix #5**: Removed Global STATE_LOCK - Deleted from main.py, updated tests
- [x] **Fix #6**: EntityRegistry Locking Optimization - 4-phase approach (read, process, write, DB)
- [x] **Fix #7**: GenreTracker Thread Safety - Added RLock, wrapped update() and as_context()
- [x] **Fix #8**: ScreenCategoryStore Locking - Moved entire maybe_learn() under lock
- [x] **Fix #9**: initialize_run() Thread Safety - Added _initialization_lock and _initialized flag

#### 📋 Thread Interaction Map
```
Main Thread (Qt GUI)
    │
    ├───> AllyCore.run_loop() [background thread]
    │       ├───> Collector (screen capture) [background thread]
    │       ├───> Scribe (vision processing) [background thread]
    │       └───> Ally LLM calls [background thread]
    │
    ├───> VoiceInputController [background thread]
    └───> QtSignalBridge (GUI updates)

Shared State:
    - StateSandbox (turn-scoped state)
    - EntityRegistry (entity resolution)
    - MemoryDB (SQLite persistence)
    - GenreTracker (genre estimation)
    - ScreenCategoryStore (category persistence)
```

### Tasks
- [x] Audit all thread boundaries
- [x] Identify shared mutable state
- [x] Review locking strategies
- [x] Implement thread safety for critical sections
- [x] Add Qt-safe event dispatching
- [ ] Review and test all fixes
- [ ] Verify no race conditions remain

### Deliverables
- [x] Thread safety audit report
- [x] Thread interaction map
- [ ] Complete test suite for concurrency
- [ ] Thread safety documentation

---

## 🐛 Phase 5: Bug Identification & Fixes

### Objective
Systematically identify and fix bugs, particularly those related to concurrency, edge cases, and error handling.

### Focus Areas
- Error handling and exception propagation
- Edge cases in state management
- Resource cleanup and memory leaks
- Configuration handling
- Input validation
- Race conditions (see Phase 4)

### Tasks
- [ ] Review error handling patterns
- [ ] Identify unhandled exceptions
- [ ] Test edge cases
- [ ] Check resource cleanup (file handles, DB connections)
- [ ] Validate configuration handling
- [ ] Add input validation

### Deliverables
- [ ] Bug audit report
- [ ] List of identified bugs
- [ ] Bug fix implementations
- [ ] Additional test cases

---

## 🔐 Phase 6: Security Review

### Objective
Identify and address potential security vulnerabilities.

### Focus Areas
- API key handling (Google Gemini)
- File path handling
- Input validation
- SQLite injection (if applicable)
- Dependency vulnerabilities
- Secret management

### Tasks
- [ ] Review API key handling
- [ ] Check file path sanitization
- [ ] Audit input validation
- [ ] Review SQLite query construction
- [ ] Check for dependency vulnerabilities
- [ ] Identify secrets in code

### Deliverables
- [ ] Security audit report
- [ ] List of security improvements
- [ ] Security best practices documentation

---

## 🧪 Phase 7: Testing Infrastructure

### Objective
Improve test coverage and testing infrastructure.

### Focus Areas
- Unit test coverage
- Integration testing
- Concurrency testing
- End-to-end testing
- Test data management
- Mocking strategies

### Tasks
- [x] Create concurrency test suite (11 tests created)
- [ ] Review existing test coverage
- [ ] Identify untested code paths
- [ ] Improve test isolation
- [ ] Add integration tests
- [ ] Implement test fixtures

### Deliverables
- [x] Concurrency test suite
- [ ] Test coverage report
- [ ] Testing improvements
- [ ] Test documentation

---

## 📈 Phase 8: Documentation

### Objective
Improve code and project documentation.

### Focus Areas
- Module-level docstrings
- Function docstrings
- Type hints
- README and project documentation
- Architecture documentation
- API documentation

### Tasks
- [ ] Review and improve docstrings
- [ ] Add missing type hints
- [ ] Update README with current information
- [ ] Create architecture documentation
- [ ] Document public APIs
- [ ] Add usage examples

### Deliverables
- [ ] Improved docstrings
- [ ] Type hints completeness
- [ ] Updated README
- [ ] Architecture documentation
- [ ] API documentation

---

## 🗺️ Phase 9: Roadmap Alignment

### Objective
Ensure the codebase aligns with the project roadmap and long-term vision.

### Focus Areas
- Feature completeness
- Technical debt
- Future extensibility
- Alignment with project goals
- Prioritization of improvements

### Tasks
- [ ] Review project roadmap
- [ ] Assess feature completeness
- [ ] Identify technical debt
- [ ] Evaluate extensibility
- [ ] Prioritize improvements

### Deliverables
- [ ] Roadmap alignment report
- [ ] Technical debt inventory
- [ ] Prioritized improvement list

---

## 📊 Progress Tracking

| Phase | Status | Priority | Owner |
|-------|--------|----------|-------|
| Phase 0: Discovery | ✅ Completed | High | Mistral |
| Phase 1: Architecture | ⏳ Pending | High | Mistral |
| Phase 2: Code Quality | ⏳ Pending | Medium | Mistral |
| Phase 3: Performance | ⏳ Pending | Medium | Mistral |
| Phase 4: Concurrency | 🟡 In Progress | **Critical** | Mistral |
| Phase 5: Bug Fixes | ⏳ Pending | High | Mistral |
| Phase 6: Security | ⏳ Pending | Medium | Mistral |
| Phase 7: Testing | 🟡 In Progress | High | Mistral |
| Phase 8: Documentation | ⏳ Pending | Low | Mistral |
| Phase 9: Roadmap | ⏳ Pending | Low | Mistral |

---

## 🎯 Priority Order

1. **Phase 4: Concurrency & Thread Safety** (CRITICAL - In Progress)
2. **Phase 5: Bug Identification & Fixes** (HIGH)
3. **Phase 7: Testing Infrastructure** (HIGH)
4. **Phase 1: Architectural Review** (HIGH)
5. **Phase 2: Code Quality & Style** (MEDIUM)
6. **Phase 3: Performance Optimization** (MEDIUM)
7. **Phase 6: Security Review** (MEDIUM)
8. **Phase 8: Documentation** (LOW)
9. **Phase 9: Roadmap Alignment** (LOW)

---

## 📝 Notes

### Thread Safety Implementation Notes
- All shared mutable state now protected by RLock (reentrant locks)
- SQLite database access serialized with application-level lock
- EventHook made thread-safe with subscriber lock
- Global STATE_LOCK removed (was confusing and inconsistently used)
- Qt-safe event hook wrapper created for GUI thread dispatching

### Testing Notes
- 11 concurrency tests created and passing
- Tests cover: StateSandbox, GenreTracker, MemoryDB, AllyCore, EntityRegistry
- Additional integration testing needed

### Merged with ZooCode Changes
- Async model loading (ClipClassifier)
- Async seeding (ScreenCategoryStore)
- Shutdown coordination (main.py)
- Logging additions across initialization
- Decorative element filtering (sandbox.py)
- Note: ZooCode's changes had removed thread safety from several files - this was preserved in merge

---

## 🔗 Related Documents

- [Thread Safety Audit Report](thread_safety_audit.md) (if created)
- [Architecture Documentation](../ARCHITECTURE.md) (if exists)
- [Project Roadmap](../../plans/) (if exists)

---

*This document is a living document and should be updated as audit phases are completed.*
