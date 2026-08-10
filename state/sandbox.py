"""The State Sandbox: a plain Python record of the current screen.

Deliberately dumb. It doesn't call any model, doesn't decide anything —
it just holds what the Scribe most recently reported so Ally has something
stable to read from.
"""

from schema.schema import ScreenElement


class StateSandbox:
    def __init__(self):
        self.turn: int = 0
        self.current_elements: list[ScreenElement] = []

    def update(self, elements: list[ScreenElement]) -> None:
        self.turn += 1
        self.current_elements = elements

    def as_context(self) -> str:
        """Compact text form for injecting into Ally's prompt."""
        if not self.current_elements:
            return "(no elements on screen)"
        return "\n".join(
            f"- [{el.id}] {el.label}: {el.description}"
            for el in self.current_elements
        )
