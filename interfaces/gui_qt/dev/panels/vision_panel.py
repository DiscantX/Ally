"""Vision Pipeline dev dock panel with multi-stage image viewer and embedded log tail.
"""
from typing import Optional, Any
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QScrollArea,
    QTextEdit,
)
from interfaces.gui_qt.theming.theme import NEUTRAL_CONTENT_THEME
from infrastructure.logger.logger import LogEntry
from interfaces.gui_qt.dev.qt_safe_logger import QtSafeLogSubscriber


class VisionPanel(QWidget):
    """Dock panel displaying pipeline images across stages with embedded log tail.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__visionPanel")
        self._images: dict[str, Any] = {}
        self._titles: dict[str, str] = {}
        self._log_tail: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Stage selector
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Stage:", self))
        self._combo = QComboBox(self)
        self._combo.setObjectName("devDock__visionCombo")
        self._combo.currentTextChanged.connect(self._on_stage_changed)
        top_bar.addWidget(self._combo)
        top_bar.addStretch(1)
        layout.addLayout(top_bar)

        # Image view area
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("devDock__visionScroll")
        self._scroll.setWidgetResizable(True)
        self._image_label = QLabel("Awaiting pipeline images...", self)
        self._image_label.setObjectName("devDock__visionImageLabel")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet(f"color: {NEUTRAL_CONTENT_THEME.fg_secondary}; background-color: {NEUTRAL_CONTENT_THEME.bg_base};")
        self._scroll.setWidget(self._image_label)
        layout.addWidget(self._scroll, stretch=3)

        # Embedded log tail (~5 lines, filtered to Vision/OCR/Classifier channels)
        self._log_text = QTextEdit(self)
        self._log_text.setObjectName("devDock__visionLogTail")
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(90)
        self._log_text.setStyleSheet(f"background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; color: {NEUTRAL_CONTENT_THEME.fg_primary}; font-family: monospace; font-size: 10px;")
        layout.addWidget(self._log_text, stretch=1)

        # Subscribe to logger for vision log tail (Qt-safe)
        self._qt_log_subscriber = QtSafeLogSubscriber(self._on_log_entry, self)

    def handle_pipeline_image(self, key: str, image: Any, title: str) -> None:
        """Stores and displays pipeline image for given stage key.
        """
        self._images[key] = image
        self._titles[key] = title or key
        if key not in [self._combo.itemText(i) for i in range(self._combo.count())]:
            self._combo.addItem(key)
        if self._combo.currentText() == key or self._combo.count() == 1:
            self._display_image(key)

    def _on_stage_changed(self, key: str) -> None:
        """Handles dropdown stage selection change.
        """
        if key in self._images:
            self._display_image(key)

    def _display_image(self, key: str) -> None:
        """Converts PIL/ndarray image to QPixmap and displays it.
        """
        img = self._images.get(key)
        if img is None:
            return
        try:
            q_img: Optional[QImage] = None
            if isinstance(img, Image.Image):
                rgb_img = img.convert("RGBA")
                data = rgb_img.tobytes("raw", "RGBA")
                q_img = QImage(data, rgb_img.width, rgb_img.height, QImage.Format.Format_RGBA8888)
            elif isinstance(img, np.ndarray):
                arr = img
                if arr.ndim == 2:
                    h, w = arr.shape
                    q_img = QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8)
                elif arr.shape[2] == 3:
                    h, w, _ = arr.shape
                    rgb = arr[..., ::-1].copy() # BGR to RGB
                    q_img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
                elif arr.shape[2] == 4:
                    h, w, _ = arr.shape
                    q_img = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888)

            if q_img is not None:
                pix = QPixmap.fromImage(q_img)
                self._image_label.setPixmap(pix)
                title = self._titles.get(key, key)
                self._image_label.setToolTip(f"Stage: {title}")
        except Exception as e:
            self._image_label.setText(f"Error rendering image: {e}")

    def _on_log_entry(self, entry: LogEntry) -> None:
        """Receives log entries and filters for vision/OCR channels.
        """
        vision_brains = {"ScreenClassifier", "ScreenBootstrapper", "LayoutOCRReader", "OCR", "ClipClassifier", "CategoryStore"}
        if entry.brain_name in vision_brains or "vision" in entry.method_name.lower():
            line = f"[{entry.brain_name}] {entry.message}"
            self._log_tail.append(line)
            if len(self._log_tail) > 5:
                self._log_tail.pop(0)
            self._log_text.setPlainText("\n".join(self._log_tail))

    def closeEvent(self, event: Any) -> None:
        """Unsubscribes logger on close.
        """
        self._qt_log_subscriber.unsubscribe()
        super().closeEvent(event)
