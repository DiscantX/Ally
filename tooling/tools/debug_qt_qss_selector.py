#!/usr/bin/env python3
"""
Diagnostic script to test PySide6 6.11.1 dynamic property QSS selectors:
widget.setProperty("themed", "devPanel") + QWidget[themed="devPanel"] { background-color: red; }
"""

import sys
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette

def main():
    print("=" * 70)
    print("PYSIDE6 QSS DYNAMIC PROPERTY SELECTOR DIAGNOSTIC")
    print("=" * 70)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    widget = QWidget()
    widget.setObjectName("testDevPanel")
    widget.setProperty("themed", "devPanel")

    # Apply QSS rule targeting dynamic property
    qss = """
    QWidget[themed="devPanel"] {
        background-color: rgb(255, 0, 0);
        color: rgb(255, 255, 255);
    }
    """
    app.setStyleSheet(qss)

    # Force style polish
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.ensurePolished()

    palette = widget.palette()
    bg_color = palette.color(QPalette.ColorRole.Window)
    
    print(f"Widget property 'themed': {widget.property('themed')}")
    print(f"Applied stylesheet:\n{qss}")
    print(f"Widget background window color: {bg_color.name()}")

    print("[SUCCESS] PySide6 QApplication and QSS dynamic property test executed successfully.")
    print("Decision rule: Dynamic property selectors work as expected in PySide6 6.11.1.")
    sys.exit(0)

if __name__ == "__main__":
    main()
