"""Tests for LogReader: from-start replay, start-at-EOF live tailing, and
truncation/restart recovery.
"""

import os
import tempfile
import threading
import time
import unittest

from collectors.log_reader import LogReader


class TestLogReaderReplay(unittest.TestCase):
    def test_read_lines_from_start_replay_unchanged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "fixture.log")
            with open(path, "w", encoding="utf-8") as f:
                f.write("line one\nline two\nline three\n")

            reader = LogReader(path, follow=False)
            lines = list(reader.read_lines())

            self.assertEqual(lines, ["line one", "line two", "line three"])

    def test_missing_file_raises_when_not_following(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "does_not_exist.log")
            reader = LogReader(path, follow=False)
            with self.assertRaises(FileNotFoundError):
                list(reader.read_lines())


class TestLogReaderStartAtEnd(unittest.TestCase):
    def test_start_at_end_skips_preexisting_and_yields_new(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "live.log")
            with open(path, "w", encoding="utf-8") as f:
                f.write("old line 1\nold line 2\n")

            reader = LogReader(path, follow=True, poll_interval=0.01, start_at_end=True)
            gen = reader.read_lines()

            results = []
            def consume():
                try:
                    results.append(next(gen))
                except Exception as e:
                    results.append(e)

            t = threading.Thread(target=consume)
            t.start()

            # Brief delay to let the generator open and seek to end before writing
            time.sleep(0.05)

            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write("new line 1\n")

                t.join(timeout=2.0)
                self.assertEqual(results, ["new line 1"])
            finally:
                gen.close()

    def test_default_start_replays_preexisting_then_follows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "live_default.log")
            with open(path, "w", encoding="utf-8") as f:
                f.write("old line 1\n")

            reader = LogReader(path, follow=True, poll_interval=0.01)  # start_at_end defaults False
            gen = reader.read_lines()
            try:
                self.assertEqual(next(gen), "old line 1")

                with open(path, "a", encoding="utf-8") as f:
                    f.write("appended line\n")
                self.assertEqual(next(gen), "appended line")
            finally:
                gen.close()


class TestLogReaderTruncation(unittest.TestCase):
    def test_recovers_from_truncate_in_place(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "restart.log")
            with open(path, "w", encoding="utf-8") as f:
                f.write("session1 line1\nsession1 line2\n")

            reader = LogReader(path, follow=True, poll_interval=0.01)
            gen = reader.read_lines()
            try:
                self.assertEqual(next(gen), "session1 line1")
                self.assertEqual(next(gen), "session1 line2")

                # Truncate in place (same inode on POSIX) and write fresh
                # content -- simulates MTGA overwriting Player.log at the
                # start of a new session via open(path, "w").
                with open(path, "w", encoding="utf-8") as f:
                    f.write("session2 line1\n")

                self.assertEqual(next(gen), "session2 line1")
            finally:
                gen.close()

    @unittest.skipIf(os.name == "nt", "os.remove on open files is not supported on Windows")
    def test_recovers_from_file_replacement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "replaced.log")
            with open(path, "w", encoding="utf-8") as f:
                f.write("session1 line1\n")

            reader = LogReader(path, follow=True, poll_interval=0.01)
            gen = reader.read_lines()
            try:
                self.assertEqual(next(gen), "session1 line1")

                # Replace the file entirely (unlink + recreate -- new inode
                # on POSIX) -- simulates a writer that recreates rather than
                # truncates in place.
                os.remove(path)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("session2 line1\n")

                self.assertEqual(next(gen), "session2 line1")
            finally:
                gen.close()


if __name__ == "__main__":
    unittest.main()
