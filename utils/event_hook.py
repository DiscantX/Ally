from typing import Callable, Any
from infrastructure.logger.logger import log, timed

MODULE_NAME = "EventHook"

class EventHook:
    def __init__(self, name: str = "") -> None:
        self.name: str = name
        self._subscribers: list[Callable[..., Any]] = []

    def connect(self, callback: Callable[..., Any]) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def disconnect(self, callback: Callable[..., Any]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    @timed
    def emit(self, *args: Any, **kwargs: Any) -> None:
        for callback in list(self._subscribers):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                log(f"Error in subscriber callback for hook '{self.name}': {e}", level="error", name="EventHook")
