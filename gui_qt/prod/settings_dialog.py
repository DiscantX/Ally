"""Minimal settings dialog for theme and personality selection.
"""
from typing import Optional, Callable
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFormLayout,
)
from cabinet.configs.config_manager import load_user_config, save_user_config
from brain.reasoning.personalities import PERSONALITIES
from gui_qt.theming.theme import Theme


class SettingsDialog(QDialog):
    """Minimal settings dialog with theme picker (Signal / Synthwave) and personality picker.
    """
    settings_saved = Signal(str, str)  # theme_name, personality_name

    def __init__(self, current_theme_name: str, current_personality: str, parent: Optional[QDialog] = None):
        super().__init__(parent)
        self.setWindowTitle("Ally Settings")
        self.setFixedSize(360, 200)
        self.setModal(True)

        self._config = load_user_config()
        self._theme_name = current_theme_name
        self._personality_name = current_personality

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        # Theme picker
        self._theme_combo = QComboBox(self)
        self._theme_combo.addItems(["Signal", "Synthwave"])
        self._theme_combo.setCurrentText(self._theme_name)
        form_layout.addRow(QLabel("Theme:"), self._theme_combo)

        # Personality picker
        self._personality_combo = QComboBox(self)
        personality_keys = list(PERSONALITIES.keys())
        self._personality_combo.addItems(personality_keys)
        self._personality_combo.setCurrentText(self._personality_name)
        form_layout.addRow(QLabel("Personality:"), self._personality_combo)

        layout.addLayout(form_layout)
        layout.addStretch(1)

        # Button box
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save & Apply", self)
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _on_save(self) -> None:
        """Saves selected configuration and emits settings_saved signal.
        """
        theme_name = self._theme_combo.currentText()
        personality_name = self._personality_combo.currentText()

        self._config["theme"] = theme_name
        self._config["default_personality"] = personality_name
        save_user_config(self._config)

        self.settings_saved.emit(theme_name, personality_name)
        self.accept()
