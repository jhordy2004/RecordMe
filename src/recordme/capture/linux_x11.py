"""Backend de captura de pantalla para Linux (X11 con soporte XFixes y Wayland experimental).

Proporciona captura rápida en servidores X11 mediante memoria compartida XShm / MSS,
con compatibilidad para portales xdg-desktop-portal en entornos Wayland.
"""

import logging
import os
import threading
from typing import Any

import numpy as np
import numpy.typing as npt

from recordme.capture.base import CaptureBackend
from recordme.capture.mss_fallback import MSSCaptureBackend
from recordme.utils.geometry import Rect

logger = logging.getLogger(__name__)


class LinuxX11CaptureBackend(CaptureBackend):
    """Backend de captura para Linux compatible con X11 y Wayland con fallback resiliente."""

    def __init__(self, display_idx: int = 0) -> None:
        self.display_idx = display_idx
        self._is_running = False
        self._lock = threading.Lock()
        self._latest_frame: npt.NDArray[np.uint8] | None = None
        self._region: Rect | None = None
        self._fps = 30
        self._backend: Any = None
        self._session_type = os.environ.get("XDG_SESSION_TYPE", "x11").lower()
        self._is_wayland = "wayland" in self._session_type or bool(os.environ.get("WAYLAND_DISPLAY"))

    def start(self, region: Rect, fps: int = 30) -> bool:
        """Inicia la captura en Linux."""
        self._region = region
        self._fps = fps
        self._is_running = True

        logger.info(
            "Iniciando LinuxX11CaptureBackend en sesión %s (Wayland=%s), región: %s",
            self._session_type,
            self._is_wayland,
            region,
        )

        try:
            # En X11 y en la mayoría de entornos Linux, MSS proporciona captura directa vía XShm
            self._backend = MSSCaptureBackend()
            success = self._backend.start(region, fps)
            if success:
                logger.info("Captura iniciada exitosamente en Linux mediante MSS / XShm.")
                return True
        except Exception as e:
            logger.warning("Error iniciando MSS en Linux: %s", e)

        # Fallback a backend Qt si MSS falla
        try:
            from recordme.capture.qt_fallback import QtScreenCaptureBackend

            self._backend = QtScreenCaptureBackend()
            return self._backend.start(region, fps)
        except Exception as e:
            logger.error("No se pudo iniciar ningún backend de captura en Linux: %s", e)
            return False

    def get_latest_frame(self) -> npt.NDArray[np.uint8] | None:
        """Devuelve el fotograma más reciente en formato BGR."""
        if not self._is_running or self._backend is None:
            return None
        return self._backend.get_latest_frame()

    def stop(self) -> None:
        """Detiene la captura y libera descriptores."""
        self._is_running = False
        if self._backend is not None:
            try:
                self._backend.stop()
            except Exception as e:
                logger.debug("Error deteniendo backend en Linux: %s", e)
            self._backend = None
        logger.info("LinuxX11CaptureBackend detenido.")

    def screens(self) -> list[Rect]:
        """Devuelve los monitores disponibles en el sistema X11/Linux."""
        if self._backend is not None:
            return self._backend.screens()
        fallback = MSSCaptureBackend()
        return fallback.screens()
