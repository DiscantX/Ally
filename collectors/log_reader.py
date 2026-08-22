"""General log reading and tailing utility.

Provides robust line-by-line reading for static log files (such as test fixtures)
and live file tailing (following newly appended lines in real-time logs like MTGA Player.log).
"""

import time
from typing import Generator, TextIO


class LogReader:
    """Reads lines from a log file, supporting both static parsing and live tailing."""

    def __init__(self, file_path: str, follow: bool = False, poll_interval: float = 0.1):
        self.file_path = file_path
        self.follow = follow
        self.poll_interval = poll_interval

    def read_lines(self) -> Generator[str, None, None]:
        """Yield lines from the log file as they appear or from start to finish."""
        try:
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                while True:
                    line = f.readline()
                    if not line:
                        if not self.follow:
                            break
                        time.sleep(self.poll_interval)
                        continue
                    yield line.rstrip("\r\n")
        except FileNotFoundError:
            if self.follow:
                while True:
                    time.sleep(self.poll_interval)
                    try:
                        with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                            break
                    except FileNotFoundError:
                        continue
                yield from self.read_lines()
            else:
                raise
