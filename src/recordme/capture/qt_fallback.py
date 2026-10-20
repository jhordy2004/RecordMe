"""Backend de captura de pantalla robusto basado en Qt (QScreen.grabWindow)."""

import logging
import threading
import time

import numpy as np
import numpy.typing as npt
from PySide6.QtGui import QGuiApplication, QImage, QPixmap

from recordme.capture.base import CaptureBackend
from recordme.utils.geometry import Rect, to_logical_pixels

logger = logging.getLogger(__name__)


class QtScreenCaptureBackend(CaptureBackend):
    """Captura de pantalla acelerada por Qt con soporte completo para DPI y exclusión de ventanas DWM."""

    def __init__(self) -> None:
        self._region: Rect | None = None
        self._fps: int = 30
        self._is_capturing = False
        self._thread: threading.Thread | None = None
        self._latest_frame: npt.NDArray[np.uint8] | None = None
        self._lock = threading.Lock()

    def start(self, region: Rect, fps: int = 30) -> bool:
        """Inicia el hilo de captura periódico de pantalla con Qt."""
        self._region = region.to_even()
        self._fps = max(1, fps)
        self._is_capturing = True

        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="Qt-CaptureThread")
        self._thread.start()
        logger.info("QtScreenCaptureBackend iniciado en región %s a %d FPS.", self._region, self._fps)
        return True

    def _capture_loop(self) -> None:
        """Bucle periódico que captura la porción de pantalla indicada."""
        interval = 1.0 / self._fps

        while self._is_capturing:
            start_time = time.perf_counter()
            try:
                screen = QGuiApplication.primaryScreen()
                if screen and self._region:
                    dpr = screen.devicePixelRatio()
                    # QScreen.grabWindow toma coordenadas lógicas
                    log_x = to_logical_pixels(self._region.x, dpr)
                    log_y = to_logical_pixels(self._region.y, dpr)
                    log_w = to_logical_pixels(self._region.width, dpr)
                    log_h = to_logical_pixels(self._region.height, dpr)

                    pixmap: QPixmap = screen.grabWindow(0, log_x, log_y, log_w, log_h)
                    qimg = pixmap.toImage().convertToFormat(QImage.Format.Format_BGR888)

                    width = qimg.width()
                    height = qimg.height()
                    stride = qimg.bytesPerLine()

                    if width > 0 and height > 0:
                        ptr = qimg.bits()
                        raw_buffer = np.frombuffer(ptr, dtype=np.uint8).reshape((height, stride))
                        # Recortar el padding de alineación de líneas
                        frame = raw_buffer[:, : width * 3].reshape((height, width, 3)).copy()

                        with self._lock:
                            self._latest_frame = frame
            except Exception as e:
                logger.debug("Error capturando frame con QtScreenCaptureBackend: %s", e)

            elapsed = time.perf_counter() - start_time
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def get_latest_frame(self) -> npt.NDArray[np.uint8] | None:
        """Devuelve el frame más reciente capturado."""
        with self._lock:
            return self._latest_frame

    def stop(self) -> None:
        """Detiene la captura de pantalla."""
        self._is_capturing = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None
        with self._lock:
            self._latest_frame = None
        logger.info("QtScreenCaptureBackend detenido.")

    def screens(self) -> list[Rect]:
        """Devuelve los monitores disponibles."""
        result: list[Rect] = []
        for screen in QGuiApplication.screens():
            geom = screen.geometry()
            dpr = screen.devicePixelRatio()
            result.append(
                Rect(
                    x=int(geom.x() * dpr),
                    y=int(geom.y() * dpr),
                    width=int(geom.width() * dpr),
                    height=int(geom.height() * dpr),
                ).to_even()
            )
        if not result:
            result.append(Rect(0, 0, 1920, 1080))
        return result
