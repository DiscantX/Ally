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
    QBoxLayout,
    QLabel,
    QScrollArea,
    QTextEdit,
    QFrame,
    QSizePolicy,
)
from interfaces.gui_qt.theming.theme import SLATE, SIGNAL, SYNTHWAVE, NEUTRAL_CONTENT_THEME, Theme
from theming.palettes import resolve_module_color
from infrastructure.logger.logger import LogEntry
from interfaces.gui_qt.dev.qt_safe_logger import QtSafeLogSubscriber


class VisionPanel(QWidget):
    """Dock panel displaying pipeline images across all stages simultaneously with embedded log tail.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("devDock__visionPanel")
        self._pipeline_slots: dict[str, Any] = {}
        self._log_tail: list[LogEntry] = []
        self._active_theme_name: str = "Slate"
        self._themes = {"Slate": SLATE, "Signal": SIGNAL, "Synthwave": SYNTHWAVE}
        self._theme: Any = SLATE
        self._core: Optional[Any] = None

        # QTimer for live preview polling (~750ms)
        self._live_preview_timer = QTimer(self)
        self._live_preview_timer.setInterval(750)
        self._live_preview_timer.timeout.connect(self._poll_live_preview)
        self._live_preview_timer.start()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Scrollable container for multi-stage pipeline images
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("devDock__visionScroll")
        self._scroll.setWidgetResizable(True)

        self._content_widget = QWidget(self)
        self._content_widget.setObjectName("devDock__visionContent")
        self._content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Phase 0 Verification: QBoxLayout.Direction.TopToBottom / LeftToRight works correctly for QBoxLayout.setDirection()
        self._is_vertical: bool = True
        initial_vertical = self.height() > self.width()
        self._is_vertical = initial_vertical
        self._pipeline_layout = QBoxLayout(
            QBoxLayout.Direction.TopToBottom if self._is_vertical else QBoxLayout.Direction.LeftToRight
        )
        self._pipeline_layout.setContentsMargins(4, 4, 4, 4)
        self._pipeline_layout.setSpacing(6)
        self._content_widget.setLayout(self._pipeline_layout)
        self._scroll.setWidget(self._content_widget)
        layout.addWidget(self._scroll, stretch=3)

        # Embedded log tail (~5 lines, filtered to Vision/OCR/Classifier channels)
        self._log_text = QTextEdit(self)
        self._log_text.setObjectName("devDock__visionLogTail")
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(90)
        self._log_text.setProperty("themed", "devPanelText")
        self._log_text.style().unpolish(self._log_text)
        self._log_text.style().polish(self._log_text)
        layout.addWidget(self._log_text, stretch=1)

        # Pre-initialize standard pipeline stage slots (matching Tkinter reference)
        pipeline_defs = [
            ("live_preview", "Live Preview (Unthrottled)"),
            ("observation", "RGB PIL Image Observation"),
            ("grayscale", "Grayscale Frame"),
            ("masked_grayscale", "ROI-Masked Grayscale Frame"),
            ("normalized_grayscale", "Luminance-Normalized Grayscale"),
            ("diff", "Absolute Difference Image"),
            ("thresh", "Thresholded Binary Change Map"),
            ("classifier_gray", "Classifier Grayscale Frame"),
            ("classifier_crop", "Anchor Crop / Draft Frame"),
            ("debug_overlay", "Annotated Debug Overlay Frame"),
        ]
        for key, title in pipeline_defs:
            self._create_pipeline_slot(key, title)

        # Subscribe to logger for vision log tail (Qt-safe)
        self._qt_log_subscriber = QtSafeLogSubscriber(self._on_log_entry, self)

    def set_active_theme(self, theme: Any) -> None:
        """Sets active theme and updates all pipeline slot cards referencing _pipeline_slots."""
        if hasattr(theme, "name"):
            self._active_theme_name = theme.name
            self._theme = theme
        elif isinstance(theme, str):
            self._active_theme_name = theme
            self._theme = self._themes.get(theme, SLATE)

        for key, slot in self._pipeline_slots.items():
            card = slot["card"]
            title_lbl = slot["title_label"]
            img_lbl = slot["image_label"]
            card.setStyleSheet(f"background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; border: 1px solid {NEUTRAL_CONTENT_THEME.border}; border-radius: 4px;")
            title_lbl.setStyleSheet(f"color: {NEUTRAL_CONTENT_THEME.accent_primary}; font-weight: bold; font-size: 10px;")
            img_lbl.setStyleSheet(f"color: {NEUTRAL_CONTENT_THEME.fg_secondary}; background-color: {NEUTRAL_CONTENT_THEME.bg_base};")
        self._refresh_log_tail()

    def _format_entry_html(self, entry: LogEntry) -> str:
        theme = self._themes.get(self._active_theme_name, SLATE)
        mod_color = resolve_module_color(self._active_theme_name, entry.brain_name)
        level_lower = entry.level.lower()
        level_color = theme.log_level_colors.get(level_lower, theme.fg_primary)
        return f'<span style="color: {mod_color};">[{entry.brain_name}]</span> <span style="color: {level_color};">{entry.message}</span>'

    def _refresh_log_tail(self) -> None:
        html_lines = [self._format_entry_html(e) for e in self._log_tail]
        self._log_text.setHtml("<br>".join(html_lines))

    def _apply_card_size_policy(self, card: QFrame, is_vertical: bool) -> None:
        """Applies appropriate size policy to pipeline card based on orientation."""
        if is_vertical:
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def _create_pipeline_slot(self, key: str, title: str) -> None:
        """Creates a UI card for a pipeline stage."""
        if key in self._pipeline_slots:
            return
        card = QFrame(self._content_widget)
        card.setObjectName(f"devDock__visionCard_{key}")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(f"background-color: {NEUTRAL_CONTENT_THEME.bg_surface}; border: 1px solid {NEUTRAL_CONTENT_THEME.border}; border-radius: 4px;")
        self._apply_card_size_policy(card, self._is_vertical)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.setSpacing(2)

        title_lbl = QLabel(title, card)
        title_lbl.setObjectName(f"devDock__visionTitle_{key}")
        title_lbl.setStyleSheet(f"color: {NEUTRAL_CONTENT_THEME.accent_primary}; font-weight: bold; font-size: 10px;")
        card_layout.addWidget(title_lbl)

        img_lbl = QLabel("Awaiting...", card)
        img_lbl.setObjectName(f"devDock__visionImage_{key}")
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_lbl.setStyleSheet(f"color: {NEUTRAL_CONTENT_THEME.fg_secondary}; background-color: {NEUTRAL_CONTENT_THEME.bg_base};")
        img_lbl.setMinimumSize(160, 120)
        img_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card_layout.addWidget(img_lbl)

        self._pipeline_layout.addWidget(card)
        self._pipeline_slots[key] = {
            "card": card,
            "title_label": title_lbl,
            "image_label": img_lbl,
            "raw_image": None,
            "title": title,
        }

    def handle_pipeline_image(self, key: str, image: Any, title: str) -> None:
        """Stores and displays pipeline image for given stage key.
        """
        if image is None:
            return
        t = title or key
        if key not in self._pipeline_slots:
            self._create_pipeline_slot(key, t)
        
        slot = self._pipeline_slots[key]
        if title:
            slot["title"] = title
            slot["title_label"].setText(title)
        slot["raw_image"] = image
        self._refresh_pipeline_slot(key)

    def _refresh_pipeline_slot(self, key: str) -> None:
        """Converts PIL/ndarray image to QPixmap and displays with proportional scaling.
        """
        slot = self._pipeline_slots.get(key)
        if not slot or slot["raw_image"] is None:
            return
        img = slot["raw_image"]
        try:
            q_img: Optional[QImage] = None
            if isinstance(img, Image.Image):
                rgb_img = img.convert("RGBA")
                data = rgb_img.tobytes("raw", "RGBA")
                q_img = QImage(data, rgb_img.width, rgb_img.height, QImage.Format.Format_RGBA8888).copy()
            elif isinstance(img, np.ndarray):
                arr = img
                if arr.ndim == 2:
                    h, w = arr.shape
                    if h > 0 and w > 0:
                        q_img = QImage(arr.tobytes(), w, h, w, QImage.Format.Format_Grayscale8).copy()
                elif arr.ndim == 3:
                    h, w, c = arr.shape
                    if h > 0 and w > 0:
                        if c == 3:
                            rgb = arr[..., ::-1].copy()  # BGR to RGB
                            q_img = QImage(rgb.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888).copy()
                        elif c == 4:
                            rgba = arr.copy()
                            q_img = QImage(rgba.tobytes(), w, h, w * 4, QImage.Format.Format_RGBA8888).copy()

            if q_img is not None and q_img.width() > 0 and q_img.height() > 0:
                pix = QPixmap.fromImage(q_img)
                img_lbl = slot["image_label"]
                
                viewport = self._scroll.viewport()
                if self._is_vertical:
                    target_w = max(100, viewport.width() - 32)
                    scaled_pix = pix.scaledToWidth(target_w, Qt.TransformationMode.SmoothTransformation)
                else:
                    target_h = max(100, viewport.height() - 32)
                    scaled_pix = pix.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)

                img_lbl.setPixmap(scaled_pix)
                img_lbl.setToolTip(f"Stage: {slot['title']} ({q_img.width()}x{q_img.height()})")
        except Exception as e:
            from infrastructure.logger.logger import log
            log("Error refreshing pipeline slot '{key}': {error}", key=key, error=str(e), level="error")
            slot["image_label"].setText(f"Error: {e}")

    def resizeEvent(self, event: Any) -> None:
        """Monitors dimension changes for responsive layout stacking and image scaling.
        """
        super().resizeEvent(event)
        self._update_layout_orientation()
        for key in self._pipeline_slots:
            self._refresh_pipeline_slot(key)

    def _update_layout_orientation(self) -> None:
        """Switches between vertical and horizontal layout stacking based on panel dimensions.
        """
        w = self.width()
        h = self.height()
        should_be_vertical = h > w

        if should_be_vertical == self._is_vertical:
            return

        self._is_vertical = should_be_vertical
        new_dir = QBoxLayout.Direction.TopToBottom if self._is_vertical else QBoxLayout.Direction.LeftToRight
        self._pipeline_layout.setDirection(new_dir)

        for slot in self._pipeline_slots.values():
            self._apply_card_size_policy(slot["card"], self._is_vertical)

    def _on_log_entry(self, entry: LogEntry) -> None:
        """Receives log entries and filters for vision/OCR channels.
        """
        vision_brains = {"ScreenClassifier", "ScreenBootstrapper", "LayoutOCRReader", "OCR", "ClipClassifier", "CategoryStore"}
        if entry.brain_name in vision_brains or "vision" in entry.method_name.lower():
            self._log_tail.append(entry)
            if len(self._log_tail) > 5:
                self._log_tail.pop(0)
            self._refresh_log_tail()

    def _poll_live_preview(self) -> None:
        """Polls screen capture statelessly via ScreenCollector for unthrottled live preview.
        """
        if self._core is None or getattr(self._core, "collector", None) is None:
            return
        collector = self._core.collector
        screen = getattr(collector, "screen", None)
        if screen is None or not hasattr(screen, "capture_bgr"):
            return
        try:
            frame_bgr = screen.capture_bgr()
            if frame_bgr is not None:
                self.handle_pipeline_image("live_preview", frame_bgr, "Live Preview (Unthrottled)")
        except Exception:
            pass

    def closeEvent(self, event: Any) -> None:
        """Stops live preview timer and unsubscribes logger on close.
        """
        if hasattr(self, "_live_preview_timer"):
            self._live_preview_timer.stop()
        self._qt_log_subscriber.unsubscribe()
        super().closeEvent(event)
