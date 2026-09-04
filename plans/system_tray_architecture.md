# System Tray & Window Lifecycle Architecture Plan

## Overview
This document outlines the architectural changes required to transition Ally into a system tray-operated application where the system tray serves as the central hub and process manager, while individual windows ([`ProdOverlayWindow`](interfaces/gui_qt/prod/overlay_window.py:28) and [`DevInspectorWindow`](interfaces/gui_qt/dev/dev_window.py:35)) can be opened and closed independently without terminating the background application.

---

## Key Components & Changes

### 1. Application-Level Lifecycle & Icon Fix (`[`main.py`](main.py:1)`)
- **Quit on Last Window Closed**: Set `app.setQuitOnLastWindowClosed(False)` so closing the overlay or dev window does not trigger an application exit.
- **Global Application Icon & AppUserModelID**:
  - Set `app.setWindowIcon(QIcon(str(icon_path)))` using `assets/ally_icon_32x32.png`.
  - On Windows, call `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ally.gaming.companion.v1")` to ensure taskbar and tray icons render correctly.

### 2. System Tray Manager (`[`interfaces/gui_qt/system_tray.py`](interfaces/gui_qt/system_tray.py)`)
- **Class**: `SystemTrayManager`
- **Responsibilities**:
  - Instantiates `QSystemTrayIcon` with `assets/ally_icon_32x32.png`.
  - Builds context menu (`QMenu`):
    - **Show/Hide Overlay**: Toggles visibility of `ProdOverlayWindow`.
    - **Open Dev Window**: Instantiates or brings `DevInspectorWindow` to front.
    - **Separator**
    - **Exit**: Invokes `shutdown_application()`.
  - Handles tray icon activation (e.g. click/double-click toggles overlay window).

### 3. Window Close Event Refactoring
- **Prod Overlay Window (`[`interfaces/gui_qt/prod/overlay_window.py`](interfaces/gui_qt/prod/overlay_window.py:146)`)**:
  - Update `closeEvent` to unregister shell bounds and call `self.hide()`, accepting the event without invoking `shutdown_application()`.
- **Dev Inspector Window (`[`interfaces/gui_qt/dev/dev_window.py`](interfaces/gui_qt/dev/dev_window.py:338)`)**:
  - Ensure `closeEvent` hides/destroys the window and resets singleton state without exiting the process.

---

## Implementation Roadmap
1. Create `[`interfaces/gui_qt/system_tray.py`](interfaces/gui_qt/system_tray.py)`.
2. Update [`main.py`](main.py:1) for tray initialization, `quitOnLastWindowClosed(False)`, and Windows AppUserModelID.
3. Modify [`interfaces/gui_qt/prod/overlay_window.py`](interfaces/gui_qt/prod/overlay_window.py:146) close behavior.
4. Test tray functionality and icon visibility.
