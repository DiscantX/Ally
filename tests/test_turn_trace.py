import unittest
from collections import deque
from brain.state.turn_trace import TurnTrace

class TestTurnTrace(unittest.TestCase):
    def test_turn_trace_dataclass(self):
        trace = TurnTrace(
            turn=1,
            timestamp=123456789.0,
            screen_name="main_menu",
            screen_confidence=0.95,
            is_draft_match=False,
            skip_scribe_reason="none",
            skip_ally=False,
            screen_category="menu",
            confirmed_facts=[],
            scribe_output=None,
            ally_output=None,
            prompt_sent_to_ally="test prompt",
            timings={"scribe": 0.1}
        )
        self.assertEqual(trace.turn, 1)
        self.assertEqual(trace.screen_name, "main_menu")
        self.assertEqual(trace.timings["scribe"], 0.1)

    def test_turn_trace_ring_buffer(self):
        traces = deque(maxlen=3)
        for i in range(5):
            traces.append(TurnTrace(
                turn=i,
                timestamp=float(i),
                screen_name=f"screen_{i}",
                screen_confidence=1.0,
                is_draft_match=False,
                skip_scribe_reason="none",
                skip_ally=False,
                screen_category=None,
                confirmed_facts=[],
                scribe_output=None,
                ally_output=None,
                prompt_sent_to_ally=None,
            ))
        self.assertEqual(len(traces), 3)
        self.assertEqual(traces[0].turn, 2)
        self.assertEqual(traces[2].turn, 4)
