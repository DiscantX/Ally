# Plan: LogReader Handle-Release Pattern for Windows File Unlocking

## Problem
On Windows, holding an open file handle (`f`) continuously across polling loops in [`LogReader.read_lines()`](collectors/log_reader.py:67) prevents external processes (or unit tests like [`test_recovers_from_file_replacement`](collectors/test_log_reader.py:84)) from deleting, unlinking, or replacing the file via `os.remove()`, raising `PermissionError: [WinError 32]`.

## Proposed Solution: Release Handle on EOF / Sleep
Refactor [`LogReader.read_lines()`](collectors/log_reader.py:67) so that when EOF is reached and the reader needs to sleep/poll for new lines:
1. Record the current file position (`file_pos = f.tell()`) and stat identity (`last_ino, last_dev`).
2. Close the file handle (`f.close()`) immediately. This releases the file lock on Windows.
3. Sleep for `poll_interval`.
4. On the next poll iteration:
   - Check file existence and stat identity at path (`_stat_identity_at_path()`).
   - If the file was removed/recreated (new inode) or truncated (size < file_pos), reset `file_pos = 0`.
   - Reopen the file, seek to `file_pos`, and continue reading.

## Benefits
- Fully compatible with Windows filesystem locking behavior (no exclusive read lock held during idle poll sleep).
- Allows external log rotation / replacement (`os.remove()`) to succeed without `PermissionError`.
- Enables [`test_recovers_from_file_replacement`](collectors/test_log_reader.py:84) to run successfully on Windows without `@unittest.skipIf`.
