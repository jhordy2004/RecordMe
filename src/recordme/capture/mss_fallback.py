"""Backend de captura de pantalla multiplataforma con mss."""

import logging
import threading
import time
from typing import Any

import mss
import numpy as np
import numpy.typing as npt

from recordme.capture.base import CaptureBackend
from recordme.utils.geometry import Rect

logger = logging.getLogger(__name__)


class MSSCaptureBackend(CaptureBackend):
    """Captura de pantalla por software usando la biblioteca mss."""

    def __init__(self) -> None:
        self._sct: Any = None
        self._region: Rect | None = None
        self._fps: int = 30
        self._is_capturing = False
        self._thread: threading.Thread | None = None
        self._latest_frame: npt.NDArray[np.uint8] | None = None
        self._lock = threading.Lock()

    def start(self, region: Rect, fps: int = 30) -> bool:
        """Inicia el hilo de captura periódico de mss."""
        self._region = region.to_even()
        self._fps = max(1, fps)
        self._is_capturing = True

        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="MSS-CaptureThread")
        self._thread.start()
        logger.info("MSS backend iniciado en región %s a %d FPS.", self._region, self._fps)
        return True

    def _capture_loop(self) -> None:
        """Bucle en hilo secundario que captura periódicamente la pantalla."""
        interval = 1.0 / self._fps
        mss_cls = getattr(mss, "MSS", mss.mss)
        with mss_cls() as sct:
            assert self._region is not None
            monitor = {
                "top": self._region.y,
                "left": self._region.x,
                "width": self._region.width,
                "height": self._region.height,
            }

            while self._is_capturing:
                start_time = time.perf_counter()
                try:
                    sct_img = sct.grab(monitor)
                    # Convertir BGRA a BGR en numpy sin canal alfa
                    img = np.array(sct_img, dtype=np.uint8)[:, :, :3]
                    with self._lock:
                        self._latest_frame = img
                except Exception as e:
                    logger.debug("Error capturando frame con mss: %s", e)

                elapsed = time.perf_counter() - start_time
                sleep_time = interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

    def get_latest_frame(self) -> npt.NDArray[np.uint8] | None:
        """Devuelve el frame más reciente capturado."""
        with self._lock:
            return self._latest_frame

    def stop(self) -> None:
        """Detiene el hilo de captura."""
        self._is_capturing = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None
        with self._lock:
            self._latest_frame = None
        logger.info("MSS backend detenido.")

    def screens(self) -> list[Rect]:
        """Devuelve los monitores detectados por mss."""
        result: list[Rect] = []
        try:
            mss_cls = getattr(mss, "MSS", mss.mss)
            with mss_cls() as sct:
                # El índice 0 en mss es "all monitors", los individuales empiezan en 1
                for mon in sct.monitors[1:]:
                    result.append(
                        Rect(
                            x=mon["left"],
                            y=mon["top"],
                            width=mon["width"],
                            height=mon["height"],
                        ).to_even()
                    )
        except Exception as e:
            logger.debug("Error listando monitores con mss: %s", e)

        if not result:
            result.append(Rect(x=0, y=0, width=1920, height=1080))
        return result
