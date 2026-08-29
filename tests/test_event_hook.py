import unittest
from utils.event_hook import EventHook

class TestEventHook(unittest.TestCase):
    def test_multiple_subscribers(self):
        hook = EventHook("test")
        received1 = []
        received2 = []
        hook.connect(lambda x: received1.append(x))
        hook.connect(lambda x: received2.append(x))
        hook.emit("hello")
        self.assertEqual(received1, ["hello"])
        self.assertEqual(received2, ["hello"])

    def test_disconnect(self):
        hook = EventHook("test")
        received = []
        cb = lambda x: received.append(x)
        hook.connect(cb)
        hook.emit("first")
        hook.disconnect(cb)
        hook.emit("second")
        self.assertEqual(received, ["first"])

    def test_exception_isolation(self):
        hook = EventHook("test")
        received = []
        def bad_cb(x):
            raise ValueError("boom")
        def good_cb(x):
            received.append(x)

        hook.connect(bad_cb)
        hook.connect(good_cb)
        hook.emit("safe")
        self.assertEqual(received, ["safe"])

    def test_zero_subscribers(self):
        hook = EventHook("test")
        # Should not raise any error
        hook.emit("nobody listening")
