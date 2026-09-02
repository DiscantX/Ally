import threading
from typing import Callable, Any
from infrastructure.logger.logger import log, timed

MODULE_NAME = "EventHook"

# Global lock for thread-safe subscriber list modifications
_subscriber_lock = threading.RLock()

class EventHook:
    def __init__(self, name: str = "") -> None:
        self.name: str = name
        self._subscribers: list[Callable[..., Any]] = []

    def connect(self, callback: Callable[..., Any]) -> None:
        """Thread-safe: adds a callback subscriber."""
        with _subscriber_lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def disconnect(self, callback: Callable[..., Any]) -> None:
        """Thread-safe: removes a callback subscriber."""
        with _subscriber_lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    @timed
    def emit(self, *args: Any, **kwargs: Any) -> None:
        """Thread-safe emit: makes a snapshot of subscribers list, then calls each.
        
        Note: Callbacks are invoked synchronously on the calling thread.
        For Qt GUI safety, use QtSafeEventHook or ensure callbacks use
        QMetaObject.invokeMethod with QueuedConnection.
        """
        # Snapshot subscribers list to avoid issues if list changes during iteration
        with _subscriber_lock:
            subscribers_snapshot = list(self._subscribers)
        
        for callback in subscribers_snapshot:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                log(f"Error in subscriber callback for hook '{self.name}': {e}", level="error", name="EventHook")
