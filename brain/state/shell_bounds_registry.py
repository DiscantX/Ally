import threading

class ShellBoundsRegistry:
    def __init__(self) -> None:
        self._bounds: dict[str, tuple[int, int, int, int]] = {}
        self._lock = threading.RLock()

    def update(self, shell_id: str, left: int, top: int, width: int, height: int) -> None:
        with self._lock:
            self._bounds[shell_id] = (left, top, width, height)

    def unregister(self, shell_id: str) -> None:
        with self._lock:
            if shell_id in self._bounds:
                del self._bounds[shell_id]

    def all_bounds(self) -> list[tuple[int, int, int, int]]:
        with self._lock:
            return list(self._bounds.values())

SHELL_BOUNDS = ShellBoundsRegistry()
