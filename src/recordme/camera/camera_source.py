"""Fuente de cámara con captura en hilo dedicado y entrega atómica de frames."""

import logging
import sys
import threading
import time
from collections.abc import Callable

import cv2
import numpy as np
import numpy.typing as npt

logger = logging.getLogger(__name__)


class CameraSource:
    """Administra la captura de la cámara en un hilo independiente."""

    def __init__(
        self,
        device_index: int = 0,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        mirror: bool = True,
    ) -> None:
        self.device_index = device_index
        self.width = width
        self.height = height
        self.fps = fps
        self.mirror = mirror

        self._cap: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._is_running = False
        self._latest_frame: npt.NDArray[np.uint8] | None = None
        self._lock = threading.Lock()
        self._on_frame_callbacks: list[Callable[[npt.NDArray[np.uint8]], None]] = []

    def add_on_frame_callback(self, callback: Callable[[npt.NDArray[np.uint8]], None]) -> None:
        """Registra un callback para recibir cada nuevo fotograma (usado por la vista previa UI)."""
        if callback not in self._on_frame_callbacks:
            self._on_frame_callbacks.append(callback)

    def remove_on_frame_callback(self, callback: Callable[[npt.NDArray[np.uint8]], None]) -> None:
        """Elimina un callback registrado."""
        if callback in self._on_frame_callbacks:
            self._on_frame_callbacks.remove(callback)

    def start(self) -> bool:
        """Abre la cámara e inicia el hilo de captura continuo."""
        try:
            backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            self._cap = cv2.VideoCapture(self.device_index, backend)
            if not self._cap.isOpened():
                # Reintentar sin backend específico
                self._cap = cv2.VideoCapture(self.device_index)

            if not self._cap.isOpened():
                logger.warning("No se pudo abrir el dispositivo de cámara con índice %d", self.device_index)
                return False

            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self._cap.set(cv2.CAP_PROP_FPS, self.fps)

            self._is_running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="Camera-Thread")
            self._thread.start()
            logger.info("CameraSource iniciada en dispositivo %d.", self.device_index)
            return True
        except Exception as e:
            logger.exception("Error al inicializar CameraSource: %s", e)
            self.stop()
            return False

    def _capture_loop(self) -> None:
        """Bucle continuo de lectura de cámara."""
        consecutive_errors = 0
        while self._is_running and self._cap is not None:
            ret, frame = self._cap.read()
            if not ret or frame is None:
                consecutive_errors += 1
                if consecutive_errors > 30:
                    logger.warning("Cámara desconectada o sin señal de video.")
                    time.sleep(0.1)
                time.sleep(0.01)
                continue

            consecutive_errors = 0
            frame_uint8: npt.NDArray[np.uint8] = np.asarray(frame, dtype=np.uint8)
            if self.mirror:
                frame_uint8 = np.asarray(cv2.flip(frame_uint8, 1), dtype=np.uint8)

            with self._lock:
                self._latest_frame = frame_uint8

            # Notificar a los observadores (vista previa UI)
            for cb in list(self._on_frame_callbacks):
                try:
                    cb(frame_uint8)
                except Exception as e:
                    logger.debug("Error en callback de frame de cámara: %s", e)

            # Pequeña pausa si los FPS son muy altos para no saturar CPU
            time.sleep(0.005)

    def get_latest_frame(self) -> npt.NDArray[np.uint8] | None:
        """Devuelve una copia del último frame BGR capturado por la cámara."""
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def stop(self) -> None:
        """Detiene la cámara y libera los recursos."""
        self._is_running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

        if self._cap is not None:
            try:
                self._cap.release()
            except Exception as e:
                logger.debug("Error liberando VideoCapture: %s", e)
            finally:
                self._cap = None

        with self._lock:
            self._latest_frame = None
        logger.info("CameraSource detenida.")
