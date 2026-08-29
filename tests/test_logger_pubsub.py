import unittest
import datetime
from infrastructure.logger import logger

class TestLoggerPubSub(unittest.TestCase):
    def test_pubsub_lifecycle(self):
        received = []
        def sub_cb(entry):
            received.append(entry)

        logger.subscribe(sub_cb)
        logger.log("Hello pubsub test", level="info", name="Main")

        self.assertTrue(len(received) > 0)
        entry = received[-1]
        self.assertEqual(entry.level, "info")
        self.assertEqual(entry.message, "Hello pubsub test")
        self.assertIsInstance(entry.timestamp, datetime.datetime)

        logger.unsubscribe(sub_cb)
        received.clear()
        logger.log("Should not be received", level="info", name="Main")
        self.assertEqual(len(received), 0)

    def test_subscriber_exception_safety(self):
        def bad_cb(entry):
            raise RuntimeError("subscriber error")

        logger.subscribe(bad_cb)
        # Should not raise exception
        logger.log("Testing exception safety in logger", level="warning", name="Main")
        logger.unsubscribe(bad_cb)
