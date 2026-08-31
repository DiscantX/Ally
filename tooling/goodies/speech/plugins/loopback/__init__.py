"""
Modular Game Audio Loopback & Acoustic Echo Cancellation (AEC) Plugin Package.
Designed for portable, third-party integration with real-time multimodal AI sessions.
"""

from .loopback import SystemLoopbackCapture, record_diagnostic_wav
from .filter import EchoCancellationFilter
from .plugin import LoopbackPluginManager

__all__ = [
    "SystemLoopbackCapture",
    "EchoCancellationFilter",
    "LoopbackPluginManager",
    "record_diagnostic_wav",
]
