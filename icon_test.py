import os
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

# CHANGE THIS to your actual file name
icon_filename = "assets\\ally_icon_32x32.png" 

print(f"File physically exists?: {os.path.exists(icon_filename)}")

pixmap = QPixmap(icon_filename)
print(f"PySide6 loaded image width: {pixmap.width()}px")
print(f"PySide6 loaded image height: {pixmap.height()}px")
print(f"Is the image null/broken?: {pixmap.isNull()}")
