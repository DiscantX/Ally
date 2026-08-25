"""Unit tests for run boundary resolution."""

import unittest
from collectors.base import RawObservation
from schema.schema import AllyOutput
from memory.triggers import resolve_run_ended


class TestRunBoundary(unittest.TestCase):
    def test_collector_signal_true_ally_none(self):
        obs = RawObservation(image=None, run_ended=True)
        ally_out = AllyOutput(analysis="done", actions=[], run_boundary="none")
        self.assertTrue(resolve_run_ended(obs, ally_out))

    def test_collector_signal_false_ally_run_ended(self):
        obs = RawObservation(image=None, run_ended=False)
        ally_out = AllyOutput(analysis="done", actions=[], run_boundary="run_ended")
        self.assertTrue(resolve_run_ended(obs, ally_out))

    def test_both_false(self):
        obs = RawObservation(image=None, run_ended=False)
        ally_out = AllyOutput(analysis="playing", actions=[], run_boundary="none")
        self.assertFalse(resolve_run_ended(obs, ally_out))

    def test_collector_takes_priority_over_ally(self):
        obs = RawObservation(image=None, run_ended=True)
        ally_out = AllyOutput(analysis="playing", actions=[], run_boundary="none")
        self.assertTrue(resolve_run_ended(obs, ally_out))


if __name__ == "__main__":
    unittest.main()
