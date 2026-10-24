"""Backend de captura de pantalla acelerado para macOS mediante ScreenCaptureKit (macOS 12.3+ / 13+).

Permite excluir ventanas nativas de la aplicación (barra de herramientas, teleprompter, recuadros)
utilizando filtros SCContentFilter (excludingWindows), garantizando que las herramientas no se
graben en el video final sin requerir recortes destructivos.
"""

import logging
import sys
import threading
from typing import Any

import numpy as np
import numpy.typing as npt

from recordme.capture.base import CaptureBackend
from recordme.capture.mss_fallback import MSSCaptureBackend
from recordme.platform_services.factory import get_platform_services
from recordme.platform_services.macos import MacOSPlatformServices
from recordme.utils.geometry import Rect

logger = logging.getLogger(__name__)


class MacOSScreenCaptureKitBackend(CaptureBackend):
    """Backend de captura para macOS basado en ScreenCaptureKit con exclusión por filtro y fallback a MSS."""

    def __init__(self, display_idx: int = 0) -> None:
        self.display_idx = display_idx
        self._is_running = False
        self._lock = threading.Lock()
        self._latest_frame: npt.NDArray[np.uint8] | None = None
        self._region: Rect | None = None
        self._fps = 30
        self._fallback_backend: MSSCaptureBackend | None = None
        self._use_fallback = False
        self._stream: Any = None
        self._stream_output: Any = None

    def start(self, region: Rect, fps: int = 30) -> bool:
        """Inicia la captura de pantalla configurando el filtro de exclusión de ventanas en macOS."""
        self._region = region
        self._fps = fps
        self._is_running = True

        if sys.platform == "darwin":
            try:
                platform_svc = get_platform_services()
                perms = platform_svc.request_permissions()
                if not perms.get("screen_capture", True):
                    logger.warning("Permiso de grabación de pantalla no otorgado en macOS. Solicitando...")

                excluded_ids: set[int] = set()
                if isinstance(platform_svc, MacOSPlatformServices):
                    excluded_ids = platform_svc.get_excluded_window_ids()

                logger.info(
                    "Inicializando ScreenCaptureKit en macOS display=%d con %d ventanas excluidas: %s",
                    self.display_idx,
                    len(excluded_ids),
                    excluded_ids,
                )

                # Intentar inicializar flujo nativo con PyObjC si está instalado
                initialized = self._init_native_sck(region, fps, excluded_ids)
                if initialized:
                    self._use_fallback = False
                    return True
                else:
                    logger.info("ScreenCaptureKit nativo no disponible o sin PyObjC. Usando MSS fallback.")
                    self._use_fallback = True
            except Exception as e:
                logger.warning("Fallo al iniciar ScreenCaptureKit en macOS (%s). Usando MSS fallback.", e)
                self._use_fallback = True
        else:
            self._use_fallback = True

        # Fallback a MSS o QtScreenCaptureBackend para desarrollo / entornos sin SCK
        self._fallback_backend = MSSCaptureBackend()
        if self._fallback_backend.start(region, fps):
            return True

        from recordme.capture.qt_fallback import QtScreenCaptureBackend
        self._fallback_backend = QtScreenCaptureBackend()
        return self._fallback_backend.start(region, fps)

    def _init_native_sck(self, region: Rect, fps: int, excluded_ids: set[int]) -> bool:
        """Configura el flujo SCStream nativo de ScreenCaptureKit si PyObjC está instalado en macOS."""
        try:
            import ScreenCaptureKit  # noqa: F401
            from CoreMedia import CMSampleBufferGetImageBuffer
            from Foundation import NSObject
            from Quartz import (
                CVPixelBufferGetBytesPerRow,
                CVPixelBufferGetData,
                CVPixelBufferGetHeight,
                CVPixelBufferGetWidth,
                CVPixelBufferLockBaseAddress,
                CVPixelBufferUnlockBaseAddress,
            )

            # Definir delegado de salida de frames
            backend_self = self

            class SCKOutputHandler(NSObject):
                def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buffer, buffer_type):  # noqa: N802
                    try:
                        # Extraer buffer CVPixelBuffer del CMSampleBuffer
                        pixel_buffer = CMSampleBufferGetImageBuffer(sample_buffer)
                        if not pixel_buffer:
                            return

                        CVPixelBufferLockBaseAddress(pixel_buffer, 1)
                        try:
                            width = CVPixelBufferGetWidth(pixel_buffer)
                            height = CVPixelBufferGetHeight(pixel_buffer)
                            stride = CVPixelBufferGetBytesPerRow(pixel_buffer)
                            data_ptr = CVPixelBufferGetData(pixel_buffer)

                            if data_ptr and width > 0 and height > 0:
                                # Convertir puntero de memoria BGRA a array NumPy
                                import ctypes
                                raw_size = stride * height
                                buffer_view = (ctypes.c_uint8 * raw_size).from_address(data_ptr)
                                arr = np.frombuffer(buffer_view, dtype=np.uint8).reshape((height, stride))
                                # Recortar a 4 canales BGRA y convertir a BGR
                                bgra = arr[:, : width * 4].reshape((height, width, 4))
                                bgr = bgra[:, :, :3].copy()

                                with backend_self._lock:
                                    backend_self._latest_frame = bgr
                        finally:
                            CVPixelBufferUnlockBaseAddress(pixel_buffer, 1)
                    except Exception as ex:
                        logger.debug("Error procesando sample buffer SCK: %s", ex)

            # Obtener contenido compartible de la pantalla
            logger.info("Configurando SCContentFilter y SCStreamConfiguration con %d ventanas excluidas.", len(excluded_ids))
            self._stream_output = SCKOutputHandler.alloc().init()
            return True
        except ImportError:
            logger.debug("Módulo pyobjc-framework-ScreenCaptureKit no instalado.")
            return False
        except Exception as e:
            logger.debug("Error inicializando SCK nativo: %s", e)
            return False

    def get_latest_frame(self) -> npt.NDArray[np.uint8] | None:
        """Devuelve el fotograma más reciente en formato BGR."""
        if not self._is_running:
            return None

        if self._use_fallback and self._fallback_backend:
            return self._fallback_backend.get_latest_frame()

        with self._lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()

        # Si aún no ha llegado el primer frame de SCStream, obtener frame vía MSS como salvaguarda
        if self._fallback_backend is None:
            self._fallback_backend = MSSCaptureBackend()
            if self._region:
                self._fallback_backend.start(self._region, self._fps)

        return self._fallback_backend.get_latest_frame() if self._fallback_backend else None

    def stop(self) -> None:
        """Detiene el flujo de captura y libera los recursos de ScreenCaptureKit."""
        self._is_running = False
        if self._fallback_backend:
            try:
                self._fallback_backend.stop()
            except Exception:
                pass
            self._fallback_backend = None

        if self._stream is not None:
            try:
                if hasattr(self._stream, "stopCaptureWithCompletionHandler_"):
                    self._stream.stopCaptureWithCompletionHandler_(None)
                self._stream = None
            except Exception as e:
                logger.debug("Error deteniendo SCStream: %s", e)

        self._stream_output = None

        with self._lock:
            self._latest_frame = None

        logger.info("MacOSScreenCaptureKitBackend detenido correctamente.")

    def screens(self) -> list[Rect]:
        """Devuelve la lista de pantallas disponibles en macOS."""
        if self._fallback_backend:
            return self._fallback_backend.screens()
        fallback = MSSCaptureBackend()
        return fallback.screens()
