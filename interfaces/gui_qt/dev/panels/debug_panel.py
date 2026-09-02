"""Debug Overlay dev dock panel displaying annotated layout boxes.
"""
from typing import Optional, Any
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from interfaces.gui_qt.theming.theme import NEUTRAL_CONTENT_THEME


class DebugPanel(QWidget):
    """Dock panel displaying the annotated debug overlay frame.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__debugPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("devDock__debugScroll")
        self._scroll.setWidgetResizable(True)

        self._image_label = QLabel("Awaiting debug overlay frame...", self)
        self._image_label.setObjectName("devDock__debugImageLabel")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet(f"color: {NEUTRAL_CONTENT_THEME.fg_secondary}; background-color: {NEUTRAL_CONTENT_THEME.bg_base};")
        self._scroll.setWidget(self._image_label)
        layout.addWidget(self._scroll)

    def handle_debug_overlay(self, frame: np.ndarray) -> None:
        """Receives BGR numpy array debug overlay frame and displays it.
        """
        if frame is None:
            return
        try:
            h, w, _ = frame.shape
            rgb = frame[..., ::-1].copy()
            q_img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(q_img)
            self._image_label.setPixmap(pix)
        except Exception as e:
            self._image_label.setText(f"Error rendering debug overlay: {e}")
