"""Debug Overlay dev dock panel displaying annotated layout boxes.
"""
from typing import Optional, Any
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from interfaces.gui_qt.theming.theme import NEUTRAL_CONTENT_THEME


class DebugPanel(QWidget):
    """Dock panel displaying the annotated debug overlay frame with robust scaling and centering.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__debugPanel")
        self._raw_frame: Optional[np.ndarray] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("devDock__debugScroll")
        self._scroll.setWidgetResizable(True)

        self._image_label = QLabel("Awaiting debug overlay frame...", self)
        self._image_label.setObjectName("devDock__debugImageLabel")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setProperty("themed", "devPanelSurface")
        self._image_label.style().unpolish(self._image_label)
        self._image_label.style().polish(self._image_label)
        self._scroll.setWidget(self._image_label)
        layout.addWidget(self._scroll)

    def set_active_theme(self, theme: Theme) -> None:
        """Sets active theme.
        """
        pass

    def handle_debug_overlay(self, frame: np.ndarray) -> None:
        """Receives BGR numpy array debug overlay frame and displays it.
        """
        if frame is None:
            return
        self._raw_frame = frame
        self._refresh_image()

    def _refresh_image(self) -> None:
        """Converts raw frame to QImage with buffer lifetime fix, scales proportionally, and centers.
        """
        if self._raw_frame is None:
            return
        try:
            frame = self._raw_frame
            h, w, _ = frame.shape
            rgb = frame[..., ::-1].copy()  # BGR to RGB
            q_img = QImage(rgb.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888).copy()
            pix = QPixmap.fromImage(q_img)

            panel_w = max(100, self.width() - 25)
            panel_h = max(100, self.height() - 25)
            scaled_pix = pix.scaled(panel_w, panel_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
            self._image_label.setPixmap(scaled_pix)
            self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        except Exception as e:
            self._image_label.setText(f"Error rendering debug overlay: {e}")

    def resizeEvent(self, event: Any) -> None:
        """Updates scaling and centering on resize.
        """
        super().resizeEvent(event)
        self._refresh_image()
