"""General log reading and tailing utility.

Provides robust line-by-line reading for static log files (such as test
fixtures) and live file tailing (following newly appended lines in
real-time logs like MTGA's Player.log).

Two independent axes control tailing behavior:

- `follow`: replay-once (False, default, unchanged) vs. keep polling for
  new lines forever (True).
- `start_at_end` (new in this pass): where a `follow=True` reader starts
  reading from. False (default, unchanged) replays everything already in
  the file before tailing new appends -- the shape needed for
  fixture-replay testing, where every line in a captured log is expected
  to come out. True starts watching only from the current end of the
  file -- the shape needed for a live Collector watching a real,
  currently-growing log, where replaying old content from a previous
  session would falsely look like it just happened.

Per docs/mtga_integration_notes.md §2.1, MTGA's Player.log is overwritten
at the start of every session (a Player-prev.log backup holds the prior
one). A live `follow=True` reader has to notice this or it either hangs
forever waiting for bytes at a file offset that no longer exists, or
silently produces short/garbage reads against a file being rewritten out
from under it.

Detection is inode-identity-based (st_dev + st_ino) as the primary
signal, with a size-vs-read-position check as a secondary one:
- Inode identity catches a writer that deletes and recreates the file
  (a genuinely new file at the same path) -- size-based detection alone
  can miss this if the new file happens to reach or exceed the old
  file's size before the next poll.
- The size check catches the narrower case of a writer that truncates
  the *same* inode in place (common for `open(path, "w")` on POSIX) --
  identity doesn't change here, so inode detection alone would miss it.
Either signal triggers the same recovery: close the stale handle, reopen
the file, and read from its start -- a restart always means unseen
content, regardless of what `start_at_end` said about the very first
open.
"""

import os
import time
from typing import Generator, TextIO


class LogReader:
    """Reads lines from a log file, supporting both static parsing and
    live tailing, with restart/truncation recovery for `follow=True`.
    """

    def __init__(
        self,
        file_path: str,
        follow: bool = False,
        poll_interval: float = 0.1,
        start_at_end: bool = False,
    ):
        self.file_path = file_path
        self.follow = follow
        self.poll_interval = poll_interval
        # Only meaningful when follow=True. Default False preserves the
        # existing from-start replay behavior for every current caller
        # (test fixtures, the file-backed single-run path in main.py).
        self.start_at_end = start_at_end

    def read_lines(self) -> Generator[str, None, None]:
        """Yield lines from the log file as they appear or from start to
        finish, per `follow`/`start_at_end` -- see module docstring."""
        current_pos = 0
        last_ino = None
        last_dev = None
        initialized = False

        while True:
            try:
                f = self._open_with_retry()
            except FileNotFoundError:
                if not self.follow:
                    raise
                time.sleep(self.poll_interval)
                continue

            try:
                if not initialized:
                    if self.follow and self.start_at_end:
                        f.seek(0, os.SEEK_END)
                        current_pos = f.tell()
                    else:
                        f.seek(0, os.SEEK_SET)
                        current_pos = 0

                    ino, dev = self._stat_identity(f)
                    last_ino, last_dev = ino, dev
                    initialized = True
                else:
                    # Check if file identity changed or truncated
                    current_ino, current_dev = self._stat_identity_at_path()
                    if current_ino is not None:
                        ino, dev = self._stat_identity(f)
                        try:
                            size_now = os.fstat(f.fileno()).st_size
                        except OSError:
                            size_now = None

                        identity_changed = (current_ino, current_dev) != (last_ino, last_dev)
                        truncated_in_place = (
                            not identity_changed
                            and size_now is not None
                            and size_now < current_pos
                        )

                        if identity_changed or truncated_in_place:
                            last_ino, last_dev = current_ino, current_dev
                            current_pos = 0

                    f.seek(current_pos)

                line = f.readline()
                if line:
                    current_pos = f.tell()
                    f.close()
                    yield line.rstrip("\r\n")
                    continue

                f.close()

                if not self.follow:
                    break

                time.sleep(self.poll_interval)

            except Exception as e:
                log("Error in log reader loop, closing file and re-raising: {error}", error=str(e), level="error")
                f.close()
                raise

    def _open_with_retry(self) -> TextIO:
        """Opens file_path. Retries on FileNotFoundError only when
        follow=True -- a live tailer should wait for a not-yet-created
        log rather than raising; a one-shot replay should raise
        immediately, exactly as before this pass."""
        while True:
            try:
                return open(self.file_path, "r", encoding="utf-8", errors="replace")
            except FileNotFoundError:
                if not self.follow:
                    raise
                time.sleep(self.poll_interval)

    @staticmethod
    def _stat_identity(f: TextIO) -> tuple[int | None, int | None]:
        try:
            st = os.fstat(f.fileno())
            return st.st_ino, st.st_dev
        except OSError:
            return None, None

    def _stat_identity_at_path(self) -> tuple[int | None, int | None]:
        try:
            st = os.stat(self.file_path)
            return st.st_ino, st.st_dev
        except OSError:
            return None, None
