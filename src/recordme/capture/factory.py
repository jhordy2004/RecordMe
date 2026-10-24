"""Fábrica para instanciar el backend de captura de pantalla adecuado con fallback resiliente."""

import logging
import sys

from recordme.capture.base import CaptureBackend
from recordme.capture.mss_fallback import MSSCaptureBackend
from recordme.capture.qt_fallback import QtScreenCaptureBackend

logger = logging.getLogger(__name__)


_dxcam_available: bool | None = None


def _check_dxcam_available() -> bool:
    global _dxcam_available
    if _dxcam_available is not None:
        return _dxcam_available
    if sys.platform != "win32":
        _dxcam_available = False
        return False
    try:
        import dxcam
        cam = dxcam.create(output_color="BGR")
        if cam is not None:
            # NO llamar a cam.release() aquí. Llamar a release() destruye el duplicador COM
            # exclusivo de DXGI y provoca fallos de acceso denegado (0x80070005) o dobles liberaciones
            # al instanciar la captura inmediatamente después. Conservar la instancia permite reutilizarla limpiamente.
            _dxcam_available = True
            return True
    except Exception as e:
        logger.info("dxcam no disponible en este entorno (%s).", e)
    _dxcam_available = False
    return False


def create_capture_backend() -> CaptureBackend:
    """Crea e inicializa el mejor backend de captura disponible en el entorno actual."""
    # 1. En Windows, intentar dxcam si es viable (con resultado cacheado para máxima velocidad)
    if _check_dxcam_available():
        try:
            from recordme.capture.windows_dxcam import WindowsDXCamBackend
            logger.info("Usando backend de captura DXGI (dxcam).")
            return WindowsDXCamBackend()
        except Exception as e:
            logger.info("Fallo al instanciar WindowsDXCamBackend (%s). Probando fallbacks...", e)

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
