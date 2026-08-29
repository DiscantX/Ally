import unittest
from brain.memory.triggers import PerspectiveConflictTrigger

class TestPerspectiveConflictTrigger(unittest.TestCase):
    def test_threshold_behavior(self):
        trigger = PerspectiveConflictTrigger(margin_threshold=2.0)
        
        # Below or equal threshold triggers
        self.assertTrue(trigger.should_trigger({"perspective_conflict_margin": 1.5}))
        self.assertTrue(trigger.should_trigger({"perspective_conflict_margin": 2.0}))
        
        # Above threshold does not trigger
        self.assertFalse(trigger.should_trigger({"perspective_conflict_margin": 2.5}))
        
        # Missing margin returns False
        self.assertFalse(trigger.should_trigger({}))

if __name__ == "__main__":
    unittest.main()
