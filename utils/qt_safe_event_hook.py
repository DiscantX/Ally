"""Qt-safe EventHook wrapper that dispatches callbacks to the Qt main thread.

This module provides a thread-safe way to connect EventHook signals to Qt slots,
ensuring that GUI updates always happen on the main Qt thread.

Usage:
    from utils.qt_safe_event_hook import QtSafeEventHook
    
    # In your Qt application:
    qt_hook = QtSafeEventHook(core.on_feedback, "on_feedback")
    qt_hook.connect(lambda msg: overlay.add_ally_message("Ally", msg))
    
    # Or use the convenience method:
    core.on_feedback.connect_qt(overlay, lambda msg: overlay.add_ally_message("Ally", msg))
"""

import threading
from typing import Callable, Any, Optional
from PySide6.QtCore import QObject, Signal, QMetaObject, Qt, Slot
from infrastructure.logger.logger import log

MODULE_NAME = "QtSafeEventHook"


class QtSignalBridge(QObject):
    """Internal QObject that bridges Python callbacks to Qt signals.
    
    Each callback type gets its own signal to ensure type safety.
    We use a generic signal that accepts any arguments.
    """
    
    # Generic signal that can handle any callback
    callback_signal = Signal(object)  # Will pass a tuple of (callback, args, kwargs)
    
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)


# Singleton bridge instance (lazy initialization)
_bridge: Optional[QtSignalBridge] = None
_bridge_lock = threading.Lock()


def _get_bridge() -> QtSignalBridge:
    """Get or create the singleton QtSignalBridge."""
    global _bridge
    if _bridge is None:
        with _bridge_lock:
            if _bridge is None:
                _bridge = QtSignalBridge()
    return _bridge


class QtSafeCallbackWrapper:
    """Wraps a callback to be invoked on the Qt main thread."""
    
    def __init__(self, callback: Callable[..., Any], name: str = ""):
        self.callback = callback
        self.name = name
        self._bridge = _get_bridge()
        # Connect our internal slot to the bridge signal
        self._bridge.callback_signal.connect(self._invoke_callback)
    
    @Slot(object)
    def _invoke_callback(self, data: tuple) -> None:
        """Internal slot that invokes the actual callback on Qt thread."""
        try:
            callback, args, kwargs = data
            callback(*args, **kwargs)
        except Exception as e:
            log("Error in Qt-safe callback '{name}': {error}", name=self.name, error=str(e), level="error")
    
    def emit(self, *args: Any, **kwargs: Any) -> None:
        """Emit the callback to be invoked on Qt main thread."""
        # Use QueuedConnection to ensure this happens on the Qt main thread
        QMetaObject.invokeMethod(
            self._bridge,
            "callback_signal",
            Qt.QueuedConnection,
            (self.callback, args, kwargs)
        )


class QtSafeEventHook:
    """A wrapper around EventHook that dispatches to Qt main thread.
    
    This class wraps an existing EventHook and ensures all connected callbacks
    are invoked on the Qt main thread, making it safe to update Qt widgets
    from background threads.
    """
    
    def __init__(self, event_hook: "EventHook", name: str = ""):  # type: ignore[name-defined]
        self._event_hook = event_hook
        self._name = name
        self._wrappers: list[QtSafeCallbackWrapper] = []
    
    def connect(self, callback: Callable[..., Any]) -> None:
        """Connect a callback to be invoked on Qt main thread."""
        wrapper = QtSafeCallbackWrapper(callback, self._name)
        self._wrappers.append(wrapper)
        self._event_hook.connect(wrapper.emit)
    
    def disconnect(self, callback: Callable[..., Any]) -> None:
        """Disconnect a callback."""
        # Find and remove the wrapper for this callback
        for i, wrapper in enumerate(self._wrappers):
            if wrapper.callback == callback:
                self._event_hook.disconnect(wrapper.emit)
                self._wrappers.pop(i)
                break
    
    def emit(self, *args: Any, **kwargs: Any) -> None:
        """Emit the event - callbacks will be invoked on Qt main thread."""
        self._event_hook.emit(*args, **kwargs)


def connect_qt_safe(event_hook: "EventHook", callback: Callable[..., Any], name: str = "") -> QtSafeCallbackWrapper:  # type: ignore[name-defined]
    """Convenience function to connect a callback to an EventHook with Qt thread safety.
    
    Returns the wrapper so it can be disconnected later.
    
    Usage:
        wrapper = connect_qt_safe(core.on_feedback, lambda msg: overlay.add_message(msg))
        # Later: event_hook.disconnect(wrapper.emit)
    """
    wrapper = QtSafeCallbackWrapper(callback, name)
    event_hook.connect(wrapper.emit)
    return wrapper
