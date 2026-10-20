"""Capa de zoom en vivo con suavizado exponencial temporal (tau filter)."""

import logging
import math

import cv2
import numpy as np
import numpy.typing as npt

logger = logging.getLogger(__name__)


class ZoomLayer:
    """Aplica zoom continuo y paneo cinemático suave centrado en coordenadas normalizadas."""

    def __init__(self, tau_seconds: float = 0.20) -> None:
        self.tau_seconds = tau_seconds
        self._current_zoom: float = 1.0
        self._current_cx: float = 0.5
        self._current_cy: float = 0.5

    @property
    def current_zoom(self) -> float:
        """Nivel actual de zoom suavizado."""
        return self._current_zoom

    @property
    def current_center(self) -> tuple[float, float]:
        """Centro actual normalizado (x, y) suavizado."""
        return (self._current_cx, self._current_cy)

    def render(
        self,
        frame: npt.NDArray[np.uint8],
        target_zoom: float,
        target_cx: float,
        target_cy: float,
        dt: float,
    ) -> npt.NDArray[np.uint8]:
        """Actualiza el filtro exponencial y aplica el recorte y escalado de zoom."""
        # 1. Filtro paso bajo exponencial
        clamped_dt = max(0.001, min(dt, 0.2))
        alpha = 1.0 - math.exp(-clamped_dt / max(0.01, self.tau_seconds))

        self._current_zoom += (target_zoom - self._current_zoom) * alpha
        self._current_cx += (target_cx - self._current_cx) * alpha
        self._current_cy += (target_cy - self._current_cy) * alpha

        # Clampeo de valores
        self._current_zoom = max(1.0, min(self._current_zoom, 5.0))
        self._current_cx = max(0.0, min(self._current_cx, 1.0))
        self._current_cy = max(0.0, min(self._current_cy, 1.0))

        # Si el zoom está prácticamente en 1.0x, evitar el remuestreo
        if self._current_zoom <= 1.01:
            return frame

        fh, fw = frame.shape[:2]
        crop_w = max(16, int(fw / self._current_zoom))
        crop_h = max(16, int(fh / self._current_zoom))

        # Centrar en (current_cx, current_cy) clampeado a bordes para no mostrar áreas negras
        center_x = int(self._current_cx * fw)
        center_y = int(self._current_cy * fh)

        x1 = max(0, min(center_x - crop_w // 2, fw - crop_w))
        y1 = max(0, min(center_y - crop_h // 2, fh - crop_h))
        x2 = x1 + crop_w
        y2 = y1 + crop_h

        cropped = frame[y1:y2, x1:x2]
        resized: npt.NDArray[np.uint8] = np.asarray(
            cv2.resize(cropped, (fw, fh), interpolation=cv2.INTER_LINEAR),
            dtype=np.uint8,
        )
        return resized
