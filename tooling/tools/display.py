import threading
import time
import cv2
import numpy as np
from PIL import Image
from infrastructure.logger import log

_lock = threading.Lock()
_latest_image = None
_thread_started = False

def _display_loop():
    global _latest_image
    window_name = "Debug Display"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    
    while True:
        with _lock:
            img = _latest_image
            
        if img is not None:
            cv2.imshow(window_name, img)
            
        key = cv2.waitKey(30) & 0xFF
        if key == 27:  # ESC to close
            break
            
    cv2.destroyAllWindows()

def show_image(image, delay=1):
    global _latest_image, _thread_started
    if image is None:
        log("Captured frame is empty. Could not display image.")
        return

    if isinstance(image, Image.Image):
        image = np.array(image)
        if len(image.shape) == 3 and image.shape[2] == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    if image.size == 0:
        log("Captured frame is empty. Could not display image.")
        return

    with _lock:
        _latest_image = image

    if not _thread_started:
        _thread_started = True
        t = threading.Thread(target=_display_loop, daemon=True)
        t.start()
