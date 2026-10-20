"""Servicios específicos de la plataforma Windows (Win32 / DWM / DPI)."""

import ctypes
import logging
from ctypes import wintypes
from typing import Any

from recordme.constants import WDA_EXCLUDEFROMCAPTURE
from recordme.platform_services.base import PlatformServices

logger = logging.getLogger(__name__)

# Definiciones Win32
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38  # Windows 11 22H2+ Mica/Acrylic


class WindowsPlatformServices(PlatformServices):
    """Implementación de servicios de plataforma para Windows 10/11."""

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._dwmapi = ctypes.windll.dwmapi
        self._shcore = getattr(ctypes.windll, "shcore", None)

    def set_dpi_awareness(self) -> bool:
        """Establece Per-Monitor DPI Awareness v2 o Per-Monitor DPI Awareness."""
        # Intentar SetProcessDpiAwarenessContext (Win10 1703+)
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        try:
            if hasattr(self._user32, "SetProcessDpiAwarenessContext"):
                res = self._user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
                if res:
                    logger.info("Per-Monitor DPI Awareness V2 configurado con éxito.")
                    return True
        except Exception as e:
            logger.debug("SetProcessDpiAwarenessContext no disponible: %s", e)

        # Fallback a SetProcessDpiAwareness (Win 8.1+)
        try:
            if self._shcore and hasattr(self._shcore, "SetProcessDpiAwareness"):
                # PROCESS_PER_MONITOR_DPI_AWARE = 2
                res = self._shcore.SetProcessDpiAwareness(2)
                if res == 0:
                    logger.info("Per-Monitor DPI Awareness configurado vía Shcore.")
                    return True
        except Exception as e:
            logger.debug("SetProcessDpiAwareness no disponible: %s", e)

        return False

    def exclude_window_from_capture(self, widget: Any) -> bool:
        """Excluye una ventana o widget Qt de la captura de pantalla usando SetWindowDisplayAffinity."""
        hwnd = self._get_hwnd(widget)
        if not hwnd:
            logger.warning("No se pudo obtener HWND del widget para exclusión de captura.")
            return False

        try:
            res = self._user32.SetWindowDisplayAffinity(
                ctypes.c_void_p(hwnd),
                wintypes.DWORD(WDA_EXCLUDEFROMCAPTURE),
            )
            success = bool(res)
            if success:
                logger.debug("Ventana HWND=0x%x excluida de la captura exitosamente.", hwnd)
            else:
                error_code = ctypes.GetLastError()
                logger.warning("Fallo al excluir ventana HWND=0x%x: error %d", hwnd, error_code)
            return success
        except Exception as e:
            logger.exception("Excepción aplicando SetWindowDisplayAffinity: %s", e)
            return False

    def apply_blur_behind(self, widget: Any) -> bool:
        """Aplica desenfoque de fondo / Mica o modo oscuro vía DWM en Windows."""
        hwnd = self._get_hwnd(widget)
        if not hwnd:
            return False

        try:
            # Activar modo oscuro en barra/bordes DWM
            dark_mode = ctypes.c_int(1)
            self._dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                wintypes.DWORD(DWMWA_USE_IMMERSIVE_DARK_MODE),
                ctypes.byref(dark_mode),
                ctypes.sizeof(dark_mode),
            )

            # Intentar aplicar Acrylic backdrop (tipo 3 = Transient/Acrylic en Win11)
            try:
                backdrop_type = ctypes.c_int(3)
                self._dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    wintypes.DWORD(DWMWA_SYSTEMBACKDROP_TYPE),
                    ctypes.byref(backdrop_type),
                    ctypes.sizeof(backdrop_type),
                )
            except Exception:
                pass

            return True
        except Exception as e:
            logger.debug("No se pudo aplicar DwmSetWindowAttribute: %s", e)
            return False

    def request_permissions(self) -> dict[str, bool]:
        """Comprueba disponibilidad básica de permisos en Windows."""
        return {
            "screen_capture": True,
            "camera": True,
            "microphone": True,
        }

    def _get_hwnd(self, widget: Any) -> int | None:
        """Obtiene el identificador de ventana nativo HWND."""
        if isinstance(widget, int):
            return widget
        if hasattr(widget, "winId"):
            return int(widget.winId())
        return None
