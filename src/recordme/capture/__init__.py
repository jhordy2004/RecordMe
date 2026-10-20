"""Módulo de captura de pantalla de RecordMe."""

from recordme.capture.base import CaptureBackend
from recordme.capture.factory import create_capture_backend
from recordme.capture.mss_fallback import MSSCaptureBackend
from recordme.capture.qt_fallback import QtScreenCaptureBackend

__all__ = [
    "CaptureBackend",
    "MSSCaptureBackend",
    "QtScreenCaptureBackend",
    "create_capture_backend",
]
