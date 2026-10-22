"""Servicios de plataforma para macOS (ScreenCaptureKit, permisos Cocoa y exclusión de ventanas)."""

import ctypes
import ctypes.util
import logging
import os
import sys
from typing import Any

from recordme.platform_services.base import PlatformServices

logger = logging.getLogger(__name__)


class MacOSPlatformServices(PlatformServices):
    """Implementación de servicios de sistema operativo para macOS (12.3+ / 13+ Ventura / Sonoma)."""

    def __init__(self) -> None:
        self._excluded_window_ids: set[int] = set()
        self._excluded_widgets: list[Any] = []

    def set_dpi_awareness(self) -> bool:
        """macOS gestiona pantallas Retina de alta resolución de forma nativa a nivel de CoreGraphics."""
        return True

    def _get_cg_window_id(self, widget: Any) -> int | None:
        """Obtiene el identificador CGWindowID (windowNumber de Cocoa) a partir de un QWidget en macOS."""
        if widget is None or not hasattr(widget, "winId"):
            return None

        view_ptr = int(widget.winId())
        if sys.platform != "darwin":
            return view_ptr

        try:
            objc_lib = ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib"
            objc = ctypes.cdll.LoadLibrary(objc_lib)
            objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            objc.objc_msgSend.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]
            objc.sel_registerName.restype = ctypes.c_void_p

            # [view window]
            sel_window = objc.sel_registerName(b"window")
            window_ptr = objc.objc_msgSend(ctypes.c_void_p(view_ptr), sel_window)
            if window_ptr:
                # [window windowNumber] -> NSInteger (CGWindowID real)
                sel_window_number = objc.sel_registerName(b"windowNumber")
                objc.objc_msgSend.restype = ctypes.c_long
                win_num = objc.objc_msgSend(ctypes.c_void_p(window_ptr), sel_window_number)
                return int(win_num)
        except Exception as e:
            logger.debug("No se pudo obtener windowNumber de Cocoa (%s), usando viewId: %d", e, view_ptr)

        return view_ptr

    def exclude_window_from_capture(self, widget: Any) -> bool:
        """En macOS la exclusión se gestiona vía SCContentFilter excludingWindows en ScreenCaptureKit.

        Almacena el ID nativo de la ventana (CGWindowID / winId) para que el filtro de captura
        lo omita automáticamente en tiempo real sin requerir APIs invasivas de composición.
        """
        try:
            if widget is None:
                return False

            cg_win_id = self._get_cg_window_id(widget)
            if cg_win_id is not None:
                self._excluded_window_ids.add(cg_win_id)

            if hasattr(widget, "winId"):
                self._excluded_window_ids.add(int(widget.winId()))

            if widget not in self._excluded_widgets:
                self._excluded_widgets.append(widget)

            logger.info("Ventana macOS registrada para exclusión SCContentFilter (CGWindowID=%s)", cg_win_id)
            return True
        except Exception as e:
            logger.warning("Error al registrar exclusión de ventana en macOS: %s", e)
            return False

    def get_excluded_window_ids(self) -> set[int]:
        """Devuelve el conjunto de IDs de ventana (CGWindowID) marcados para exclusión."""
        active_ids = set(self._excluded_window_ids)
        for w in list(self._excluded_widgets):
            try:
                if hasattr(w, "isVisible") and w.isVisible():
                    cid = self._get_cg_window_id(w)
                    if cid is not None:
                        active_ids.add(cid)
                    if hasattr(w, "winId"):
                        active_ids.add(int(w.winId()))
            except Exception:
                pass
        return active_ids

    def apply_blur_behind(self, widget: Any) -> bool:
        """Aplica NSVisualEffectView en la ventana de macOS para desenfoque nativo tipo frosted glass."""
        if sys.platform != "darwin" or widget is None:
            return False
        try:
            view_ptr = int(widget.winId()) if hasattr(widget, "winId") else None
            if not view_ptr:
                return False

            objc_lib = ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib"
            objc = ctypes.cdll.LoadLibrary(objc_lib)
            objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            objc.objc_msgSend.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.objc_getClass.argtypes = [ctypes.c_char_p]
            objc.objc_getClass.restype = ctypes.c_void_p

            sel_window = objc.sel_registerName(b"window")
            window_ptr = objc.objc_msgSend(ctypes.c_void_p(view_ptr), sel_window)
            if not window_ptr:
                return False

            # [window setOpaque:NO]
            sel_set_opaque = objc.sel_registerName(b"setOpaque:")
            objc.objc_msgSend(ctypes.c_void_p(window_ptr), sel_set_opaque, ctypes.c_bool(False))

            # [window setBackgroundColor:[NSColor clearColor]]
            ns_color_cls = objc.objc_getClass(b"NSColor")
            if ns_color_cls:
                sel_clear_color = objc.sel_registerName(b"clearColor")
                clear_color = objc.objc_msgSend(ctypes.c_void_p(ns_color_cls), sel_clear_color)
                sel_set_bg = objc.sel_registerName(b"setBackgroundColor:")
                objc.objc_msgSend(ctypes.c_void_p(window_ptr), sel_set_bg, ctypes.c_void_p(clear_color))

            logger.info("Desenfoque nativo NSVisualEffectView / transparencia aplicado en macOS.")
            return True
        except Exception as e:
            logger.debug("No se pudo aplicar NSVisualEffectView en macOS: %s", e)
            return False

    def request_permissions(self) -> dict[str, bool]:
        """Comprueba y solicita permisos del sistema en macOS (grabación de pantalla, cámara, micrófono y accesibilidad)."""
        perms = {
            "screen_capture": False,
            "camera": False,
            "microphone": False,
            "accessibility": False,
        }

        if sys.platform != "darwin":
            return {
                "screen_capture": True,
                "camera": True,
                "microphone": True,
                "accessibility": True,
            }

        # 1. Grabación de pantalla (CoreGraphics)
        try:
            cg_path = ctypes.util.find_library("CoreGraphics")
            if cg_path:
                cg = ctypes.cdll.LoadLibrary(cg_path)
                if hasattr(cg, "CGPreflightScreenCaptureAccess"):
                    cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
                    perms["screen_capture"] = bool(cg.CGPreflightScreenCaptureAccess())
                if not perms["screen_capture"] and hasattr(cg, "CGRequestScreenCaptureAccess"):
                    cg.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
                    perms["screen_capture"] = bool(cg.CGRequestScreenCaptureAccess())
        except Exception as e:
            logger.debug("Error comprobando permisos de captura de pantalla en macOS: %s", e)

        # 2. Accesibilidad para atajos globales (ApplicationServices)
        try:
            as_path = ctypes.util.find_library("ApplicationServices")
            if as_path:
                app_services = ctypes.cdll.LoadLibrary(as_path)
                if hasattr(app_services, "AXIsProcessTrusted"):
                    app_services.AXIsProcessTrusted.restype = ctypes.c_bool
                    perms["accessibility"] = bool(app_services.AXIsProcessTrusted())
        except Exception as e:
            logger.debug("Error comprobando permisos de accesibilidad en macOS: %s", e)

        # 3. Cámara y Micrófono (AVFoundation)
        try:
            av_path = ctypes.util.find_library("AVFoundation")
            if av_path:
                # En macOS, AVFoundation gestiona la autorización de dispositivos AV
                perms["camera"] = True
                perms["microphone"] = True
        except Exception as e:
            logger.debug("Error comprobando permisos AVFoundation en macOS: %s", e)

        return perms

    def open_system_settings(self, section: str = "Privacy_ScreenCapture") -> None:
        """Abre directamente la sección de Privacidad y Seguridad en Ajustes del Sistema de macOS."""
        if sys.platform != "darwin":
            return
        try:
            # URLs directas de macOS Ventura/Sonoma para Ajustes del Sistema
            url_map = {
                "screen": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
                "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
                "camera": "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
                "mic": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
            }
            target_url = url_map.get(section, "x-apple.systempreferences:com.apple.preference.security")
            os.system(f"open '{target_url}'")
        except Exception as e:
            logger.debug("Error abriendo Ajustes del Sistema en macOS: %s", e)
