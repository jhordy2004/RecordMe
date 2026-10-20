"""Servicios de plataforma para Linux (Stub X11/Wayland)."""

import logging
from typing import Any

from recordme.platform_services.base import PlatformServices

logger = logging.getLogger(__name__)


class LinuxPlatformServices(PlatformServices):
    """Implementación base para Linux."""

    def set_dpi_awareness(self) -> bool:
        """En Linux la escala depende de X11/Wayland y Qt."""
        return True

    def exclude_window_from_capture(self, widget: Any) -> bool:
        """En Linux no hay API nativa para excluir ventanas propias en la captura general."""
        logger.warning("Exclusión de ventana no soportada directamente por el servidor gráfico en Linux.")
        return False

    def apply_blur_behind(self, widget: Any) -> bool:
        """En Linux el blur depende del compositor de ventanas (KWin, Picom, etc.)."""
        return False

    def request_permissions(self) -> dict[str, bool]:
        """Linux normalmente no requiere permisos a nivel de OS salvo Portales Wayland."""
        return {
            "screen_capture": True,
            "camera": True,
            "microphone": True,
        }
