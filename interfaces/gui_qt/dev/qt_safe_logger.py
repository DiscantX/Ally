"""Qt-safe logger subscriber infrastructure for dev inspector panels.

This module provides a thread-safe way for Qt GUI components to receive
log entries from background threads without violating Qt's thread affinity rules.
"""

from typing import Callable, Any, Optional
from PySide6.QtCore import QObject, Signal, Slot
from infrastructure.logger.logger import LogEntry, subscribe, unsubscribe


class QtLogEntryBridge(QObject):
    """QObject that emits LogEntry objects for Qt-safe delivery."""
    
    log_entry_received = Signal(object)  # Emits LogEntry
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        subscribe(self._forward_to_qt)

    def _forward_to_qt(self, entry: LogEntry) -> None:
        """Forward log entry to Qt main thread via signal."""
        self.log_entry_received.emit(entry)

    def unsubscribe(self) -> None:
        """Unsubscribe from the global logger."""
        unsubscribe(self._forward_to_qt)


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
    
    @Slot(object)
    def _handle_entry(self, entry: LogEntry) -> None:
        """Handle log entry on Qt main thread."""
        try:
            self._callback(entry)
        except Exception as e:
            from infrastructure.logger.logger import log
            log("Error in Qt-safe log callback: {error}", error=str(e), level="error")
    
    def unsubscribe(self) -> None:
        """Unsubscribe from the Qt bridge signal."""
        try:
            self._bridge.log_entry_received.disconnect(self._handle_entry)
        except Exception:
            pass
