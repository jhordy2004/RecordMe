"""Fábrica de servicios de plataforma según el sistema operativo actual."""

import sys

from recordme.platform_services.base import PlatformServices
from recordme.platform_services.linux import LinuxPlatformServices
from recordme.platform_services.macos import MacOSPlatformServices
from recordme.platform_services.windows import WindowsPlatformServices


def get_platform_services() -> PlatformServices:
    """Devuelve la instancia correspondiente a la plataforma del sistema."""
    if sys.platform == "win32":
        return WindowsPlatformServices()
    elif sys.platform == "darwin":
        return MacOSPlatformServices()
    else:
        return LinuxPlatformServices()
