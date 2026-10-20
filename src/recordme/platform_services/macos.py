"""Servicios de plataforma para macOS (Stub para compatibilidad con la interfaz)."""

import logging
from typing import Any

from recordme.platform_services.base import PlatformServices

logger = logging.getLogger(__name__)


class MacOSPlatformServices(PlatformServices):
    """Implementación base para macOS (ScreenCaptureKit y Cocoa)."""

    def set_dpi_awareness(self) -> bool:
        """macOS gestiona Retina automáticamente."""
        return True

    def exclude_window_from_capture(self, widget: Any) -> bool:
        """En macOS la exclusión se gestiona vía SCContentFilter excludingWindows."""
        logger.info("Exclusión en macOS delegada a filtro de ScreenCaptureKit.")
        return True

    def apply_blur_behind(self, widget: Any) -> bool:
        """Aplica NSVisualEffectView en macOS."""
        return False

    def request_permissions(self) -> dict[str, bool]:
        """Solicita permisos de grabación, cámara y micrófono en macOS."""
        return {
            "screen_capture": False,
            "camera": False,
            "microphone": False,
        }
