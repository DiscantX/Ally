import sys
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtGui import QIcon

app = QApplication(sys.argv)

print("--- DIAGNOSTICS ---")
print(f"1. Is System Tray Available?: {QSystemTrayIcon.isSystemTrayAvailable()}")

# Create a minimal tray icon using a built-in OS icon (rules out file path issues)
tray = QSystemTrayIcon()
app_style = app.style()
default_icon = app_style.standardIcon(app_style.StandardPixmap.SP_MessageBoxInformation)
tray.setIcon(default_icon)
tray.setToolTip("Test Tray Icon")
tray.show()

print(f"2. Is Tray Icon Visible property true?: {tray.isVisible()}")
print("-------------------")
print("If the script doesn't close immediately, the icon should be in your tray right now.")
print("Press Ctrl+C in your terminal to exit.")

sys.exit(app.exec())
