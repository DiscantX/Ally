"""Scores which of the four PERSPECTIVES is dominant right now, purely
from text Ally already has access to (recent narrative-buffer turns,
touched-entity facts) -- deliberately NOT from numeric game telemetry,
since Ally has no such thing for any game and adding one would be
genre-specific. This is a local, deterministic, zero-API-call heuristic
-- consistent with the project's "screen classification must not add an
extra API call" principle, generalized here to perspective scoring.

Keyword lists live in [`configs/template/perspective_keywords.json`](configs/template/perspective_keywords.json) (config-driven, not hardcoded) so they can be tuned without a code
change -- flagged as a first-pass heuristic, expected to need revisiting
against real playtesting, same category as `looks_like_real_text()`'s
alnum-ratio heuristic.
"""

import json
import os
from dataclasses import dataclass

from brain.reasoning.perspectives import PERSPECTIVES
from infrastructure.logger import log, timed

KEYWORDS_FILE = "configs/template/perspective_keywords.json"
BASELINE_PERSPECTIVE = "Phronesis"


@dataclass
class PerspectiveScore:
    primary: str
    primary_score: float
    secondary: str
    secondary_score: float

    @property
    def conflict_margin(self) -> float:
        """How close the top two scores are. Small margin = a loud,
        genuinely-tense internal conflict; large margin = one framing
        clearly dominates."""
        return self.primary_score - self.secondary_score


class PerspectiveEngine:
    def __init__(self, keywords_path: str = KEYWORDS_FILE):
        self._keywords: dict[str, list[str]] = self._load_keywords(keywords_path)

    @timed
    def _load_keywords(self, path: str) -> dict[str, list[str]]:
        if not os.path.exists(path):
            log("No perspective keywords file at {path} -- every perspective will score 0 (Phronesis baseline always wins).", path=path)
            return {name: [] for name in PERSPECTIVES}
        with open(path, "r") as f:
            data = json.load(f)
        return {name: data.get(name, []) for name in PERSPECTIVES}

    def score(self, recent_turns: list[str], entity_facts: list[str]) -> PerspectiveScore:
        """recent_turns: plain narrative-buffer summary strings (see
        [`NarrativeMemoryManager.get_recent_turn_texts()`](brain/memory/narrative.py)). entity_facts:
        plain fact strings from this turn's touched entities. Both are
        joined and lowercased once; keyword matching is a simple
        substring count, not NLP."""
        haystack = " ".join(recent_turns + entity_facts).lower()

        scores: dict[str, float] = {name: 0.0 for name in PERSPECTIVES}
        scores[BASELINE_PERSPECTIVE] = 1.0  # baseline default, matches original design's starting state

        for name, keywords in self._keywords.items():
            for kw in keywords:
                scores[name] += haystack.count(kw.lower())

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        primary_name, primary_score = ranked[0]
        secondary_name, secondary_score = ranked[1] if len(ranked) > 1 else ranked[0]

        if secondary_score == 0.0 and primary_score > 0.0:
            secondary_name, secondary_score = primary_name, primary_score

        return PerspectiveScore(
            primary=primary_name, primary_score=primary_score,
            secondary=secondary_name, secondary_score=secondary_score,
        )

    def as_context(self, score: PerspectiveScore) -> str:
        primary_def = PERSPECTIVES[score.primary]["definition"]
        if score.primary == score.secondary:
            return f"Dominant internal framing right now: {score.primary} -- {primary_def}"
        secondary_def = PERSPECTIVES[score.secondary]["definition"]
        return (
            f"Two internal framings are in tension right now:\n"
            f"- Primary ({score.primary}): {primary_def}\n"
            f"- Secondary ({score.secondary}): {secondary_def}\n"
            "Let your established personality decide how much weight each gets -- "
            "you don't need to resolve this explicitly out loud, just let it color your reaction."
        )
