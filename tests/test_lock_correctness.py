# test_chat_lock_release.py
import time
import threading
import unittest
from unittest.mock import MagicMock

import main


class TestChatLockRelease(unittest.TestCase):
    def test_chat_does_not_block_capture_loop(self):
        # Simulate a slow ally.chat() call
        slow_ally = MagicMock()

        def slow_chat(**kwargs):
            time.sleep(0.5)
            return MagicMock(response="ok")

        slow_ally.chat.side_effect = slow_chat

        acquired_during_chat = []

        def try_acquire_during_chat():
            time.sleep(0.05)  # let chat start first
            got_lock = main.STATE_LOCK.acquire(timeout=0.1)
            acquired_during_chat.append(got_lock)
            if got_lock:
                main.STATE_LOCK.release()

        t = threading.Thread(target=try_acquire_during_chat)
        t.start()
        slow_ally.chat(
            elements_context="", entities_context="", genre_context="",
            memory_context="", personality="", question="test",
        )
        t.join()

        self.assertTrue(
            acquired_during_chat[0],
            "STATE_LOCK was held during the network call -- fix regressed",
        )


if __name__ == "__main__":
    unittest.main()