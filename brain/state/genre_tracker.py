"""Tracks the running best guess at the game's genre for this run.

Deliberately not part of StateSandbox: the Sandbox is turn-scoped and
gets fully overwritten by update() every turn, but genre shouldn't
regress just because one frame was ambiguous (e.g. a cutscene). This
holds the best guess seen so far and locks once confidence clears the
threshold, so Ally gets a stable genre instead of it flickering turn to
turn.
"""

import threading
from dataclasses import dataclass


@dataclass
class GenreEstimate:
    guess: str = "unknown"
    confidence: float = 0.0
    locked: bool = False


class GenreTracker:
    def __init__(self, lock_threshold: float = 0.75):
        self._lock = threading.RLock()
        self.lock_threshold = lock_threshold
        self.estimate = GenreEstimate()

    def update(self, guess: str, confidence: float) -> GenreEstimate:
        """Called once per turn with the Scribe's fresh guess. No-op once
        locked -- stop moving the target on Ally mid-run.
        
        Thread-safe: holds lock while updating estimate.
        """
        with self._lock:
            if self.estimate.locked:
                return self.estimate

            if confidence > self.estimate.confidence:
                self.estimate.guess = guess
                self.estimate.confidence = confidence

            if self.estimate.confidence >= self.lock_threshold:
                self.estimate.locked = True

            # Return a copy to avoid external modification
            return GenreEstimate(
                guess=self.estimate.guess,
                confidence=self.estimate.confidence,
                locked=self.estimate.locked
            )

    def as_context(self) -> str:
        """Thread-safe: holds lock while reading estimate."""
        with self._lock:
            if self.estimate.confidence == 0.0:
                return "unknown (not yet determined)"
            certainty = "confirmed" if self.estimate.locked else "tentative guess"
            return f"{self.estimate.guess} ({certainty})"