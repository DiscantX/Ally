"""Ported unchanged from the NeowsEye prototype. Fully game-agnostic:
given any window title, resolves and manipulates its client-area
geometry. Windows-only (pywin32) -- see note in screen_collector.py
about keeping this behind the generic Collector interface so a future
Linux/macOS capture backend can drop in without touching callers.
"""

import time
import win32con
import win32gui
from infrastructure.logger import log, timed


class ClientRect:
    _first_setup_done = False

    @timed
    def __init__(self, window_title="Slay the Spire"):
        start_t = time.perf_counter()
        self.window_title = window_title
        self.handle = self._get_window_handle(window_title)

        if self.handle:
            self._set_rect_properties()
        duration = time.perf_counter() - start_t
        if not ClientRect._first_setup_done:
            ClientRect._first_setup_done = True
            log("Initialized window manager for '{title}' in {duration:.4f}s (handle={handle})", title=window_title, duration=duration, handle=self.handle)

    @timed
    def _get_window_handle(self, window_title):
        handle = win32gui.FindWindow(None, window_title)
        if not handle:
            log("Window not found: {window_title}", window_title=window_title)
            return None
        return handle

    def _set_rect_properties(self):
        client_rect = win32gui.GetClientRect(self.handle)
        client_left, client_top = win32gui.ClientToScreen(self.handle, (client_rect[0], client_rect[1]))
        client_right, client_bottom = win32gui.ClientToScreen(self.handle, (client_rect[2], client_rect[3]))

        self.left = client_left
        self.top = client_top
        self.width = client_right - client_left
        self.height = client_bottom - client_top

    def move_to_top_left(self):
        if self.handle:
            window_rect = win32gui.GetWindowRect(self.handle)
            win_left, win_top, win_right, win_bottom = window_rect

            if win_left == 0 and win_top == 0:
                return

            width = win_right - win_left
            height = win_bottom - win_top

            win32gui.MoveWindow(self.handle, 0, 0, width, height, win32con.SWP_NOZORDER | win32con.SWP_NOSIZE)
            self._set_rect_properties()

    def bring_to_foreground(self):
        if self.handle:
            if win32gui.IsIconic(self.handle):
                win32gui.ShowWindow(self.handle, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self.handle)

    def refresh(self) -> bool:
        """Re-resolve this window's client-area geometry from its live handle.
        Call this every turn (it's a couple of cheap win32 calls) so a window
        that's been dragged to another monitor or resized after startup gets
        picked up -- capture_bgr() otherwise keeps reading whatever pixel
        region it was first calibrated to, forever, silently.

        Returns False (without raising) if the handle is no longer valid --
        e.g. the game was closed -- so callers can treat "window is gone" the
        same way they already treat "window was never found."
        """
        if not self.handle or not win32gui.IsWindow(self.handle):
            return False
        try:
            self._set_rect_properties()
            return True
        except Exception:
            return False

    def is_foreground(self) -> bool:
        """True if this window is currently the OS-level focused window.
        Cheap (one win32 call, no frame capture) -- meant to be checked
        before doing any capture work at all, not just before commenting on
        a captured frame."""
        if not self.handle:
            return False
        return win32gui.GetForegroundWindow() == self.handle

    def set_always_on_top(self, enable=True):
        if self.handle:
            insert_after = win32con.HWND_TOPMOST if enable else win32con.HWND_NOTOPMOST
            win32gui.SetWindowPos(self.handle, insert_after, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
