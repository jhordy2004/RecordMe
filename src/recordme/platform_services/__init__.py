"""Servicios e integraciones nativas con el sistema operativo."""

from recordme.platform_services.base import PlatformServices
from recordme.platform_services.factory import get_platform_services

__all__ = ["PlatformServices", "get_platform_services"]
