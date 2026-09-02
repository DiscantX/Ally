# test_chat_lock_release.py
import time
import threading
import unittest
from unittest.mock import MagicMock

from brain.reasoning.core import AllyCore


class TestChatLockRelease(unittest.TestCase):
    def test_chat_does_not_block_capture_loop(self):
        """Test that AllyCore.state_lock is not held during slow LLM operations.
        
        This test verifies that the locking discipline in AllyCore allows
        concurrent access to shared state even when LLM calls are in progress.
        """
        # Create a minimal AllyCore instance
        core = AllyCore(image_path="test.png")  # image_path mode doesn't need collector
        
        # Simulate a slow chat call
        slow_ally = MagicMock()
        
        def slow_chat(**kwargs):
            time.sleep(0.5)
            return MagicMock(response="ok")
        
        slow_ally.chat_stream.side_effect = slow_chat
        core.ally = slow_ally
        
        # Initialize to set up state
        core.initialize_run()
        
        acquired_during_chat = []
        
        def try_acquire_during_chat():
            time.sleep(0.05)  # let chat start first
            # Try to acquire the core's state_lock
            got_lock = core.state_lock.acquire(timeout=0.1)
            acquired_during_chat.append(got_lock)
            if got_lock:
                core.state_lock.release()
        
        # Start the send_message in a thread (which will call chat_stream)
        def trigger_send_message():
            core.send_message("test")
            time.sleep(0.6)  # Wait for chat to complete
        
        t_chat = threading.Thread(target=trigger_send_message)
        t_lock = threading.Thread(target=try_acquire_during_chat)
        
        t_chat.start()
        t_lock.start()
        
        t_chat.join()
        t_lock.join()
        
        # The lock should be acquirable during the LLM call
        # because send_message releases the lock before calling ally.chat_stream
        self.assertTrue(
            len(acquired_during_chat) > 0 and acquired_during_chat[0],
            "state_lock was held during the LLM call -- locking discipline regressed"
        )


if __name__ == "__main__":
    unittest.main()