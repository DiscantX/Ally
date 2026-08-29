import unittest
import tempfile
import os
from brain.reasoning.perspective_engine import PerspectiveEngine, PerspectiveScore


class TestPerspectiveEngine(unittest.TestCase):
    def test_scoring_heuristics_ataraxia(self):
        engine = PerspectiveEngine()
        # "died" and "failed" are Ataraxia keywords
        score = engine.score(["we died and failed the run"], ["game over"])
        self.assertEqual(score.primary, "Ataraxia")
        self.assertGreater(score.primary_score, 1.0)

    def test_neutral_empty_baseline(self):
        engine = PerspectiveEngine()
        score = engine.score([], [])
        self.assertEqual(score.primary, "Phronesis")
        self.assertEqual(score.primary_score, 1.0)
        self.assertEqual(score.secondary, "Phronesis")
        self.assertEqual(score.secondary_score, 1.0)
        self.assertEqual(score.conflict_margin, 0.0)

    def test_conflict_margin(self):
        score = PerspectiveScore(primary="Ataraxia", primary_score=3.0, secondary="Phronesis", secondary_score=1.0)
        self.assertEqual(score.conflict_margin, 2.0)

    def test_missing_keywords_file_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = os.path.join(tmpdir, "nonexistent.json")
            engine = PerspectiveEngine(keywords_path=bad_path)
            score = engine.score(["died"], ["failed"])
            self.assertEqual(score.primary, "Phronesis")
            self.assertEqual(score.primary_score, 1.0)


if __name__ == "__main__":
    unittest.main()
