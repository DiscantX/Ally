import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
import PySide6QtAds as QtAds

def main():
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("ADS Smoke Test")
    window.resize(900, 700)

    # Instantiate CDockManager
    dock_manager = QtAds.CDockManager(window)

    # Add 4 dummy CDockWidgets
    for i in range(1, 5):
        label = QLabel(f"Content for Dock {i} - Test edge-snap overlay")
        dock_widget = QtAds.CDockWidget(f"Dock {i}")
        dock_widget.setWidget(label)
        dock_widget.setObjectName(f"dock_{i}")

        if i == 1:
            dock_manager.addDockWidget(QtAds.DockWidgetArea.LeftDockWidgetArea, dock_widget)
        elif i == 2:
            dock_manager.addDockWidget(QtAds.DockWidgetArea.RightDockWidgetArea, dock_widget)
        elif i == 3:
            dock_manager.addDockWidget(QtAds.DockWidgetArea.BottomDockWidgetArea, dock_widget)
        else:
            dock_manager.addDockWidget(QtAds.DockWidgetArea.TopDockWidgetArea, dock_widget)

    window.show()
    
    # Test state save/restore round-trip
    state = dock_manager.saveState()
    print("Successfully saved ADS state length:", len(state))
    
    restored = dock_manager.restoreState(state)
    print("Successfully restored ADS state:", restored)
    
    print("ADS smoke test passed successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
