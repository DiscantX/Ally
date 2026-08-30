import ctypes
from infrastructure.logger.logger import log, timed

MODULE_NAME = "CaptureExclusion"

@timed
def exclude_hwnd_from_capture(hwnd: int) -> bool:
    """Excludes a window from screen captures using the Windows DWM API (SetWindowDisplayAffinity)."""
    try:
        # WDA_EXCLUDEFROMCAPTURE = 0x00000011
        result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
        if result == 0:
            log(f"SetWindowDisplayAffinity failed for hwnd {hwnd}", level="warning")
            return False
        return True
    except Exception as e:
        log(f"Failed to exclude hwnd {hwnd} from capture: {e}", level="debug")
        return False
