"""Backend de captura de pantalla para Windows utilizando DXGI Desktop Duplication (dxcam)."""

import logging
import threading
from typing import Any

import dxcam
import numpy as np
import numpy.typing as npt

from recordme.capture.base import CaptureBackend
from recordme.utils.geometry import Rect

logger = logging.getLogger(__name__)


class WindowsDXCamBackend(CaptureBackend):
    """Captura de pantalla acelerada por GPU usando DXGI Desktop Duplication."""

    def __init__(self, device_idx: int = 0, output_idx: int = 0) -> None:
        self.device_idx = device_idx
        self.output_idx = output_idx
        self._camera: Any = None
        self._is_capturing = False
        self._latest_frame: npt.NDArray[np.uint8] | None = None
        self._lock = threading.Lock()
        self._region: Rect | None = None

    def start(self, region: Rect, fps: int = 30) -> bool:
        """Inicia la captura con dxcam en modo de captura continua."""
        try:
            self._region = region.to_even()
            logger.info("Inicializando dxcam en pantalla %d, región: %s, fps: %d", self.output_idx, self._region, fps)

            # dxcam espera región como (left, top, right, bottom)
            # Si es pantalla completa o región específica
            dxcam_region = (
                self._region.x,
                self._region.y,
                self._region.x + self._region.width,
                self._region.y + self._region.height,
            )

            self._camera = dxcam.create(
                device_idx=self.device_idx,
                output_idx=self.output_idx,
                output_color="BGR",
            )
            if self._camera is None:
                logger.error("dxcam.create devolvió None.")
                return False

            self._camera.start(
                target_fps=fps,
                video_mode=True,
                region=dxcam_region,
            )
            self._is_capturing = True
            logger.info("dxcam iniciado correctamente.")
            return True
        except Exception as e:
            logger.exception("Error al iniciar dxcam: %s", e)
            self.stop()
            return False

    def get_latest_frame(self) -> npt.NDArray[np.uint8] | None:
        """Obtiene el último frame capturado desde dxcam."""
        if not self._is_capturing or self._camera is None:
            return None

        try:
            frame = self._camera.get_latest_frame()
            if frame is not None:
                with self._lock:
                    self._latest_frame = frame
            with self._lock:
                return self._latest_frame
        except Exception as e:
            logger.debug("Error leyendo frame de dxcam: %s", e)
            with self._lock:
                return self._latest_frame

    def stop(self) -> None:
        """Detiene la captura y libera el objeto dxcam."""
        if self._camera is not None:
            try:
                if self._camera.is_capturing:
                    self._camera.stop()
            except Exception as e:
                logger.debug("Error deteniendo cámara dxcam: %s", e)
            finally:
                self._camera = None
        self._is_capturing = False
        with self._lock:
            self._latest_frame = None
        logger.info("dxcam detenido.")

    def screens(self) -> list[Rect]:
        """Obtiene los monitores disponibles."""
        # dxcam outputs o Win32 fallback
        try:
            outputs = dxcam.output_info()
            result: list[Rect] = []
            for _info in outputs:
                # Si info tiene resolución
                res = Rect(x=0, y=0, width=1920, height=1080)
                result.append(res)
            if result:
                return result
        except Exception as e:
            logger.debug("No se pudo obtener output_info de dxcam: %s", e)
        return [Rect(x=0, y=0, width=1920, height=1080)]
