import cv2

def show_image(image):
  if image is None or image.size == 0:
    print("[Neow's Eye] Captured frame is empty. Could not display image.")
    return

  window_name = "Debug Display"

  # WINDOW_AUTOSIZE forces the window to match the exact dimensions of the image buffer
  cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

  cv2.imshow(window_name, image)
  cv2.waitKey(0)
  cv2.destroyAllWindows()