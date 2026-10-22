"""Fábrica de servicios de plataforma según el sistema operativo actual."""

import sys

from recordme.platform_services.base import PlatformServices
from recordme.platform_services.linux import LinuxPlatformServices
from recordme.platform_services.macos import MacOSPlatformServices
from recordme.platform_services.windows import WindowsPlatformServices

_instance: PlatformServices | None = None


def get_platform_services() -> PlatformServices:
    """Devuelve la instancia correspondiente a la plataforma del sistema."""
    global _instance
    if _instance is None:
        if sys.platform == "win32":
            _instance = WindowsPlatformServices()
        elif sys.platform == "darwin":
            _instance = MacOSPlatformServices()
        else:
            _instance = LinuxPlatformServices()
    return _instance
