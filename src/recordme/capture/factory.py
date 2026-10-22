"""Fábrica para instanciar el backend de captura de pantalla adecuado con fallback resiliente."""

import logging
import sys

from recordme.capture.base import CaptureBackend
from recordme.capture.mss_fallback import MSSCaptureBackend
from recordme.capture.qt_fallback import QtScreenCaptureBackend

logger = logging.getLogger(__name__)


def create_capture_backend() -> CaptureBackend:
    """Crea e inicializa el mejor backend de captura disponible en el entorno actual."""
    # 1. En Windows, intentar dxcam si es viable
    if sys.platform == "win32":
        try:
            import dxcam
            # Prueba de humo de inicialización
            test_cam = dxcam.create(output_color="BGR")
            if test_cam is not None:
                # Comprobar si puede capturar sin error de acceso denegado
                test_cam.release()
                from recordme.capture.windows_dxcam import WindowsDXCamBackend
                logger.info("Usando backend de captura DXGI (dxcam).")
                return WindowsDXCamBackend()
        except Exception as e:
            logger.info("dxcam no disponible en este entorno (%s). Probando fallbacks...", e)

    # 2. En macOS, usar backend ScreenCaptureKit con exclusión por SCContentFilter
    if sys.platform == "darwin":
        try:
            from recordme.capture.macos_screencapturekit import MacOSScreenCaptureKitBackend

            logger.info("Usando backend de captura ScreenCaptureKit en macOS.")
            return MacOSScreenCaptureKitBackend()
        except Exception as e:
            logger.info("ScreenCaptureKit no disponible (%s). Probando fallbacks...", e)

    # 3. En Linux, usar backend X11/Wayland con MSS/XShm
    if sys.platform.startswith("linux"):
        try:
            from recordme.capture.linux_x11 import LinuxX11CaptureBackend

            logger.info("Usando backend de captura LinuxX11CaptureBackend.")
            return LinuxX11CaptureBackend()
        except Exception as e:
            logger.info("Backend Linux no disponible (%s). Probando fallbacks...", e)

    # 4. Fallback estándar multiplataforma: mss
    try:
        import mss
        mss_cls = getattr(mss, "MSS", mss.mss)
        with mss_cls() as sct:
            if len(sct.monitors) > 0:
                sct.grab(sct.monitors[0])
                logger.info("Usando backend de captura MSS.")
                return MSSCaptureBackend()
    except Exception as e:
        logger.info("mss no disponible o restringido (%s). Usando fallback QtScreenCaptureBackend...", e)

    # 5. Fallback universal garantizado: QtScreenCaptureBackend
    logger.info("Usando backend de captura QtScreenCaptureBackend.")
    return QtScreenCaptureBackend()
