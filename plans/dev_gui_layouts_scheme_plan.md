# Dev GUI Window Layouts Scheme Architecture Plan

## Overview
This document outlines the architecture and implementation plan for saving, loading, resetting, and shipping default window layouts for the PySide6 Dev Inspector (`DevInspectorWindow`) utilizing the Qt Advanced Docking System (ADS).

---

## 1. Current Layout Storage & State
- **How it is currently stored**: The current layout is **not hardcoded**. It is managed dynamically by `PySide6QtAds.CDockManager`.
- **Persistence**:
  - Across sessions, geometry and ADS state are stored via `QSettings("Ally", "DevInspectorWindow")` (`geometry` and `adsState` keys).
  - An in-memory default state (`self._default_ads_state`) is captured immediately after all dock panels are registered in `_setup_docks()`.
  - The "Reset Layout" action restores `_default_ads_state` and removes `adsState` from `QSettings`.

---

## 2. Menu Structure Recommendation
We evaluated two options for integrating layout management into `DevInspectorWindow._setup_menus()`:
1. **Option A: Submenu under "View"** (`View -> Layouts -> [Save Layout..., Load Layout..., Reset Layout, Default...]`)
2. **Option B: Dedicated "Layout" Menu Dropdown** next to "View" (`&Layout -> [Save Current Layout..., Load Layout..., Reset to Default, Shipped Layouts...]`)

**Recommendation**: **Option B (Dedicated "Layout" Menu)** or **Option A Submenu under "View"**. Specifically, placing a **"Layouts" submenu under the existing "View" menu** or a dedicated **"Layout" top-level menu** keeps panel visibility toggles clearly separated from layout configurations (matching professional tools like Qt Creator and Visual Studio). Let's use a **dedicated "Layout" top-level menu** or a **"Layouts" submenu under "View"**. Let's go with a dedicated **"Layout" menu** for maximum discoverability and clean separation of concerns.

---

## 3. Shipping Default Layouts & Plug-in Mechanism
To ship default pre-configured layouts with the program:
1. **Storage Location**:
   - Template/Shipped layouts will reside in `cabinet/configs/layouts/system`.
   - User-saved custom layouts will reside in `cabinet/configs/layouts/user`

2. **Serialization**:
   - `CDockManager.saveState()` returns a `QByteArray`.
   - This can be converted to base64-encoded text or binary `.dat` / `.json` format containing the state bytes and metadata.
3. **Plug-in Mechanism on Startup / Reset**:
   - On first run (when no `adsState` exists in `QSettings`), check for a shipped default layout file (e.g., `cabinet/configs/layouts/system/default_dev_layout.json`).
   - If present, load its base64 state bytes and apply via `_dock_manager.restoreState()`.
   - If absent, fall back to code-constructed default docks.

---

## 4. Workflow Diagram

```mermaid
graph TD
    A[Start DevInspectorWindow] --> B{QSettings has adsState?}
    B -- Yes --> C[Restore user saved state]
    B -- No --> D{Shipped default layout exists?}
    D -- Yes --> E[Load shipped layout from cabinet configs template layouts]
    D -- No --> F[Use code-constructed default dock arrangement]
    C --> G[Ready]
    E --> G
    F --> G
    
    G --> H[User opens Layout Menu]
    H --> I[Save Current Layout]
    H --> J[Load Custom Layout]
    H --> K[Reset to Default]
    I --> L[Serialize CDockManager state to JSON file]
    J --> M[Open QFileDialog and restoreState]
    K --> N[Restore shipped default layout state]
