# Root Directory Reorganization Plan

> **Status:** Architectural Proposal (Approved with Feedback)
> **Target File:** [`plans/root_directory_reorganization_plan.md`](plans/root_directory_reorganization_plan.md:1)
> **Reference Documents:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md:1), [`docs/ally_decision_log.md`](docs/ally_decision_log.md:1), [`CLAUDE.md`](CLAUDE.md:1)

---

## 1. Executive Summary & Rationale

The root directory of Ally has accumulated over 21 top-level directories ([`ally/`](ally/ally_agent.py:1), [`collectors/`](collectors/base.py:1), [`configs/`](configs/config_manager.py:1), [`data/`](data/:1), [`docs/`](docs/ARCHITECTURE.md:1), [`goodies/`](goodies/geneology.py:1), [`gui/`](gui/chat_drawer.py:1), [`interpretation/`](interpretation/scribe.py:1), [`llm/`](llm/gemini_provider.py:1), [`logger/`](logger/logger.py:1), [`memory/`](memory/db.py:1), [`plans/`](plans/CLAUDE_LED_TASK_pyside6_gui_rewrite.md:1), [`plugins/`](plugins/mtga/__init__.py:1), [`prompts/`](prompts/ally.py:1), [`schema/`](schema/schema.py:1), [`snapshots/`](snapshots/:1), [`state/`](state/entity_registry.py:1), [`tests/`](tests/test_ally.py:1), [`tools/`](tools/display.py:1), [`vision/`](vision/change_detector.py:1), [`visuals/`](visuals/header.py:1)). While this flat structure facilitated early rapid prototyping, it scatters core cognitive and perceptual modules across the root namespace, obscuring the central architectural metaphor of Ally: an **AI game companion structured around brain analogies and clean domain boundaries**.

This plan outlines a domain-driven reorganization that:
1. Groups all cognitive, perceptual, memory, and state-tracking functions into a central [`brain/`](brain/__init__.py:1) module, reflecting the brain analogy principles documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md:1) and [`docs/ally_decision_log.md`](docs/ally_decision_log.md:1).
2. Consolidates peripheral modules into logical top-level domain directories ([`ingestion/`](ingestion/:1), [`interfaces/`](interfaces/:1), [`infrastructure/`](infrastructure/:1), [`storage/`](storage/:1), [`tooling/`](tooling/:1)).
3. Establishes a direct, atomic refactoring of `import` statements across all consuming files ([`main.py`](main.py:1), [`run.py`](run.py:1), [`tests/`](tests/:1), etc.) during each phase without utilizing temporary backwards-compatible proxy shims.

---

## 2. Current Root Layout Audit vs. Proposed Grouped Hierarchy

### Current Root Audit

| Current Directory / File | Architectural Responsibility | Proposed Location |
| :--- | :--- | :--- |
| [`ally/`](ally/ally_agent.py:1) | Ally reasoning agent, personalities, core runner | [`brain/reasoning/`](brain/reasoning/ally_agent.py:1) |
| [`vision/`](vision/change_detector.py:1) | Superior colliculus, screen classifier, OCR, layout reader | [`brain/perception/`](brain/perception/vision/change_detector.py:1) |
| [`interpretation/`](interpretation/scribe.py:1) | Scribe perception agent (Gemini vision) | [`brain/perception/`](brain/perception/interpretation/scribe.py:1) |
| [`memory/`](memory/db.py:1) | Narrative memory, personality memory, save tracker | [`brain/memory/`](brain/memory/manager.py:1) |
| [`state/`](state/entity_registry.py:1) | State sandbox, entity registry, genre tracker | [`brain/state/`](brain/state/sandbox.py:1) |
| [`prompts/`](prompts/ally.py:1) | LLM system prompts for Ally, Scribe, narrative | [`brain/knowledge/`](brain/knowledge/prompts/ally.py:1) |
| [`schema/`](schema/schema.py:1) | Pydantic data models and schemas | [`brain/knowledge/`](brain/knowledge/schema/schema.py:1) |
| [`collectors/`](collectors/base.py:1) | Screen capture, log reader, window manager | [`ingestion/collectors/`](ingestion/collectors/base.py:1) |
| [`plugins/`](plugins/mtga/__init__.py:1) | Game-specific plugins (e.g. MTGA parser/resolver) | [`ingestion/plugins/`](ingestion/plugins/mtga/__init__.py:1) |
| [`gui/`](gui/chat_drawer.py:1) | Tkinter chat drawer, overlay API, settings | [`interfaces/gui/`](interfaces/gui/tkinter_app.py:1) |
| [`visuals/`](visuals/header.py:1) | Header components and visual styling | [`interfaces/visuals/`](interfaces/visuals/header.py:1) |
| [`llm/`](llm/gemini_provider.py:1) | Gemini LLM provider wrapper and model lister | [`infrastructure/llm/`](infrastructure/llm/gemini_provider.py:1) |
| [`logger/`](logger/logger.py:1) | Stack-frame inspection logging utility | [`infrastructure/logger/`](infrastructure/logger/logger.py:1) |
| [`configs/`](configs/config_manager.py:1) | Configuration manager and game templates | [`storage/configs/`](storage/configs/config_manager.py:1) |
| [`data/`](data/:1) | Runtime data and database storage | [`storage/data/`](storage/data/:1) |
| [`snapshots/`](snapshots/:1) | Captured screen snapshots and fixtures | [`storage/snapshots/`](storage/snapshots/:1) |
| [`tools/`](tools/display.py:1) | CLI tooling, coordinate inspection, init config | [`tooling/tools/init_config.py`](tooling/tools/init_config.py:1) |
| [`goodies/`](goodies/geneology.py:1) | Experimental genetic personality algorithms | [`tooling/goodies/`](tooling/goodies/geneology.py:1) |
| [`tests/`](tests/test_ally.py:1) | Full integration and unit test suite | [`tests/`](tests/test_ally.py:1) (Root level) |
| [`docs/`](docs/ARCHITECTURE.md:1) | Architecture docs, decision log, roadmap | [`docs/`](docs/ARCHITECTURE.md:1) (Root level) |
| [`plans/`](plans/CLAUDE_LED_TASK_pyside6_gui_rewrite.md:1) | Architectural plans and task tracking | [`plans/`](plans/CLAUDE_LED_TASK_pyside6_gui_rewrite.md:1) (Root level) |

---

## 3. Deep-Dive Breakdown of the Brain Directory Structure ([`brain/`](brain/__init__.py:1))

Following the design principles established in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md:1) (Section 6) and [`docs/ally_decision_log.md`](docs/ally_decision_log.md:1), the system core models a synthetic cognitive architecture. The proposed [`brain/`](brain/__init__.py:1) directory organizes these subcomponents using functional python modules with brain-analogy docstring annotations:

```text
brain/
├── __init__.py
├── perception/                      # V1, Dorsal/Ventral streams, Superior Colliculus
│   ├── __init__.py
│   ├── change_detector.py           # Superior colliculus (pre-Scribe SSIM/ROI filter)
│   ├── screen_classifier.py         # Local anchor/draft screen identification
│   ├── screen_bootstrapper.py       # Automated layout drafting
│   ├── layout.py                    # Layout loading and UIElement management
│   ├── layout_reader.py             # Tesseract local OCR reader
│   ├── geometry.py                  # Coordinate conversion (normalized <-> pixel)
│   ├── ocr.py                       # Text validation and OCR helpers
│   └── scribe.py                    # V1 / Ventral stream (Gemini vision perception agent)
├── state/                           # Sensory buffer & iconic memory
│   ├── __init__.py
│   ├── sandbox.py                   # StateSandbox (per-turn fact store & trust framings)
│   ├── entity_registry.py           # Semantic memory / entity resolution index
│   └── genre_tracker.py             # Stable running genre estimation
├── memory/                          # Hippocampus & Prefrontal cortex memory tiers
│   ├── __init__.py
│   ├── manager.py                   # MemoryManager (unified Narrative & Personality coordinator)
│   ├── narrative.py                 # Tiered lossy compression (short -> medium -> long -> cross-session)
│   ├── personality.py               # Multi-resolution personality master journal -> digest -> micro
│   ├── save_tracker.py              # Save ID resolution & run boundary heuristics
│   ├── triggers.py                  # Composite flush and run-ended trigger conditions
│   └── db.py                        # SQLite persistence layer (MemoryDB)
├── reasoning/                       # Prefrontal Cortex reasoning core
│   ├── __init__.py
│   ├── ally_agent.py                # Ally reasoning agent (Gemini; air-gapped from raw pixels)
│   ├── personalities.py             # Named second-person tone definitions
│   └── core.py                      # AllyCore central orchestration loop and thread synchronization
└── knowledge/                       # Static knowledge bases
    ├── __init__.py
    ├── prompts/                     # System prompts (Ally, Scribe, narrative, personality)
    └── schema/                      # Pydantic validation schemas & models
```

### Architectural Mapping Justification
- **[`brain/perception/`](brain/perception/vision/change_detector.py:1):** Combines [`vision/`](vision/change_detector.py:1) and [`interpretation/`](interpretation/scribe.py:1) into a unified perceptual pipeline. This makes the data flow from retina capture -> superior colliculus filter -> V1/stream extraction immediately clear to developers.
- **[`brain/state/`](brain/state/sandbox.py:1):** Houses [`state/`](state/sandbox.py:1) components acting as the sensory buffer and entity registry, cleanly separated from long-term memory.
- **[`brain/memory/`](brain/memory/manager.py:1):** Encapsulates all persistence, tiered narrative summarization, and personality redistillation governed by Task-Positive Network (TPN) vs Default Mode Network (DMN) principles.
- **[`brain/reasoning/`](brain/reasoning/ally_agent.py:1):** Houses [`ally/`](ally/ally_agent.py:1), keeping Ally's decision engine and [`ally/core.py`](ally/core.py:1) orchestration isolated from perception.
- **[`brain/knowledge/`](brain/knowledge/prompts/ally.py:1):** Centralizes static instruction sets ([`prompts/`](prompts/ally.py:1)) and data contracts ([`schema/schema.py`](schema/schema.py:1)) used across cognitive operations.

---

## 4. Breakdown of Non-Brain Groupings

To keep the root workspace clean and modular, peripheral domains are grouped into clear top-level directories:

### 1. [`ingestion/`](ingestion/:1) (Collectors & Plugins)
- **[`collectors/`](collectors/base.py:1)**: Contains [`collectors/base.py`](collectors/base.py:1), [`collectors/configured_collector.py`](collectors/configured_collector.py:1), [`collectors/log_reader.py`](collectors/log_reader.py:1), [`collectors/screen_collector.py`](collectors/screen_collector.py:1), and [`collectors/window_manager.py`](collectors/window_manager.py:1).
- **[`plugins/`](plugins/mtga/__init__.py:1)**: Contains game-specific ingestion plugins such as [`plugins/mtga/`](plugins/mtga/__init__.py:1).

### 2. [`interfaces/`](interfaces/:1) (User Presentation Layer)
- **[`gui/`](gui/tkinter_app.py:1)**: Contains [`gui/tkinter_app.py`](gui/tkinter_app.py:1), [`gui/chat_drawer.py`](gui/chat_drawer.py:1), [`gui/overlay_api.py`](gui/overlay_api.py:1), and [`gui/settings_window.py`](gui/settings_window.py:1).
- **[`visuals/`](visuals/header.py:1)**: Contains [`visuals/header.py`](visuals/header.py:1) and layout graphics.

### 3. [`infrastructure/`](infrastructure/:1) (Shared External Services)
- **[`llm/`](llm/gemini_provider.py:1)**: Contains [`llm/gemini_provider.py`](llm/gemini_provider.py:1) and [`llm/model_lister.py`](llm/model_lister.py:1).
- **[`logger/`](logger/logger.py:1)**: Contains [`logger/logger.py`](logger/logger.py:1) with dynamic stack-frame inspection.

### 4. [`storage/`](storage/:1) (Persistence & Configuration Data)
- **[`configs/`](configs/config_manager.py:1)**: Contains [`configs/config_manager.py`](configs/config_manager.py:1) and templates.
- **[`data/`](data/:1)**: Runtime databases and files.
- **[`snapshots/`](snapshots/:1)**: Captured frame fixtures and test images.

### 5. [`tooling/`](tooling/:1) (Developer & Maintenance Scripts)
- **[`tools/`](tools/display.py:1)**: Contains [`tools/init_config.py`](tools/init_config.py:1), [`tools/inspect_coords.py`](tools/inspect_coords.py:1), [`tools/display.py`](tools/display.py:1), and [`tools/update_docs.py`](tools/update_docs.py:1).
- **[`goodies/`](goodies/geneology.py:1)**: Contains experimental utilities like [`goodies/geneology.py`](goodies/geneology.py:1).

### 6. Supporting Root Directories (Unchanged)
- **[`tests/`](tests/test_ally.py:1)**: Integration and unit tests ([`tests/run_tests.py`](tests/run_tests.py:1)).
- **[`docs/`](docs/ARCHITECTURE.md:1)**: Living architectural documentation ([`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md:1), [`docs/ally_decision_log.md`](docs/ally_decision_log.md:1)).
- **[`plans/`](plans/CLAUDE_LED_TASK_pyside6_gui_rewrite.md:1)**: Task planning and architectural proposals ([`plans/root_directory_reorganization_plan.md`](plans/root_directory_reorganization_plan.md:1)).

---

## 5. Import Refactoring & Migration Strategy

No temporary package aliasing or backwards-compatible proxy shims will be used. Instead, the reorganization relies on **direct, atomic refactoring of `import` statements** across all consuming files ([`main.py`](main.py:1), [`run.py`](run.py:1), [`tests/`](tests/:1), plugins, and GUI modules) during each phase. 

Whenever a directory or module is moved to its new target path (e.g. from [`ally/core.py`](ally/core.py:1) to [`brain/reasoning/core.py`](brain/reasoning/core.py:1)), all corresponding import references across the codebase are updated immediately and atomically in the same change unit.

---

## 6. Pros, Cons, and Tradeoffs

| Aspect | Assessment | Mitigation / Reasoning |
| :--- | :--- | :--- |
| **Cognitive Load** | **Major Improvement:** Developers immediately understand module boundaries (cognition vs ingestion vs interface). | Aligns code layout directly with [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md:1). |
| **Import Path Depth** | **Minor Tradeoff:** Import statements become slightly deeper (e.g. [`brain.perception.scribe`](brain/perception/scribe.py:1)). | Direct imports maintain clarity and avoid runtime indirection or magic shims. |
| **Test Suite Stability** | **Managed Risk:** Moving test targets requires updating import paths across [`tests/`](tests/test_ally.py:1). | Executed atomically per phase and validated immediately via [`tests/run_tests.py`](tests/run_tests.py:1). |
| **Git History** | **Managed Risk:** File moves can disrupt git blame if not done with git-aware tooling ([`git mv`](git mv)). | Use [`git mv`](git mv) during implementation to preserve file history. |

---

## 7. Execution Checklist & Phased Rollout

- [ ] **Phase 1: Core Cognitive & Brain Directory Setup**
  - Create [`brain/`](brain/__init__.py:1) and its subdirectories ([`brain/perception/`](brain/perception/__init__.py:1), [`brain/state/`](brain/state/__init__.py:1), [`brain/memory/`](brain/memory/__init__.py:1), [`brain/reasoning/`](brain/reasoning/__init__.py:1), [`brain/knowledge/`](brain/knowledge/__init__.py:1)).
  - Move [`ally/`](ally/ally_agent.py:1), [`vision/`](vision/change_detector.py:1), [`interpretation/`](interpretation/scribe.py:1), [`memory/`](memory/db.py:1), [`state/`](state/entity_registry.py:1), [`prompts/`](prompts/ally.py:1), and [`schema/`](schema/schema.py:1) contents into [`brain/`](brain/__init__.py:1) subdirectories via [`git mv`](git mv).
  - Perform direct atomic updates to all import statements in [`main.py`](main.py:1), [`run.py`](run.py:1), and [`tests/`](tests/:1) referencing these modules.
  - Run [`tests/run_tests.py`](tests/run_tests.py:1) to verify core cognitive tests pass.

- [ ] **Phase 2: Peripheral Domains Consolidation (`ingestion/`, `interfaces/`, `infrastructure/`, `storage/`, `tooling/`)**
  - Create top-level directories: [`ingestion/`](ingestion/:1), [`interfaces/`](interfaces/:1), [`infrastructure/`](infrastructure/:1), [`storage/`](storage/:1), [`tooling/`](tooling/:1).
  - Move [`collectors/`](collectors/base.py:1), [`plugins/`](plugins/mtga/__init__.py:1) into [`ingestion/`](ingestion/:1).
  - Move [`gui/`](gui/tkinter_app.py:1), [`visuals/`](visuals/header.py:1) into [`interfaces/`](interfaces/:1).
  - Move [`llm/`](llm/gemini_provider.py:1), [`logger/`](logger/logger.py:1) into [`infrastructure/`](infrastructure/:1).
  - Move [`configs/`](configs/config_manager.py:1), [`data/`](data/:1), [`snapshots/`](snapshots/:1) into [`storage/`](storage/:1).
  - Move [`tools/`](tools/display.py:1), [`goodies/`](goodies/geneology.py:1) into [`tooling/`](tooling/:1).
  - Update all importing files across the workspace atomically.
  - Run full test suite via [`tests/run_tests.py`](tests/run_tests.py:1) to ensure 100% test pass rate.

- [ ] **Phase 3: Documentation Updates & Architecture Alignment**
  - Update [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md:1) to document the new [`brain/`](brain/__init__.py:1) directory hierarchy and subsystem groupings (`perception`, `state`, `memory`, `reasoning`, `knowledge`), as well as top-level peripheral domains ([`ingestion/`](ingestion/:1), [`interfaces/`](interfaces/:1), [`infrastructure/`](infrastructure/:1), [`storage/`](storage/:1), [`tooling/`](tooling/:1)).
  - Update [`docs/adding_a_new_game.md`](docs/adding_a_new_game.md:1) to reflect new plugin import paths under [`ingestion/plugins/`](ingestion/plugins/mtga/__init__.py:1) and updated configuration locations under [`storage/configs/`](storage/configs/config_manager.py:1).
  - Update [`docs/ally_decision_log.md`](docs/ally_decision_log.md:1) to record the architectural decision regarding root directory reorganization and brain-analogy module structuring.
  - Update [`docs/roadmap.md`](docs/roadmap.md:1) and other markdown documentation files in [`docs/`](docs/) (`docs/changelog.md`, etc.) to reference correct module paths and package layouts.
