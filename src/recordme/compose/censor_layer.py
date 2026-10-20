"""Capa de censura en tiempo real con modos blur gaussiano, pixelado y color sólido."""

import logging
from collections.abc import Sequence

import cv2
import numpy as np
import numpy.typing as npt

from recordme.core.render_state import CensorRegion
from recordme.utils.geometry import Rect

logger = logging.getLogger(__name__)


class CensorLayer:
    """Aplica censura sobre las regiones especificadas en el fotograma antes de componer zoom o cámara."""

    def render(
        self,
        frame: npt.NDArray[np.uint8],
        regions: Sequence[CensorRegion],
        capture_region: Rect,
    ) -> npt.NDArray[np.uint8]:
        """Aplica desenfoque, pixelado o recuadro sólido sobre cada región activa."""
        if not regions:
            return frame

        out = frame.copy()
        fh, fw = out.shape[:2]

        for reg in regions:
            if not reg.active:
                continue

            # Mapear coordenadas de pantalla física a coordenadas relativas del frame
            rx = reg.rect.x - capture_region.x
            ry = reg.rect.y - capture_region.y
            rw = reg.rect.width
            rh = reg.rect.height

            # Clampear a los límites del frame
            x1 = max(0, min(rx, fw - 1))
            y1 = max(0, min(ry, fh - 1))
            x2 = max(x1, min(rx + rw, fw))
            y2 = max(y1, min(ry + rh, fh))

            if (x2 - x1) < 2 or (y2 - y1) < 2:
                continue

            roi = out[y1:y2, x1:x2]

            if reg.mode == "blur":
                # Kernel impar proporcional al tamaño o intensidad fijada
                k = max(3, reg.blur_strength | 1)
                blurred = cv2.GaussianBlur(roi, (k, k), 0)
                out[y1:y2, x1:x2] = blurred

            elif reg.mode == "pixelate":
                # Reducción por factor de pixelado y ampliación con vecino más cercano
                p = max(4, reg.pixel_size)
                small_w = max(1, (x2 - x1) // p)
                small_h = max(1, (y2 - y1) // p)
                small = cv2.resize(roi, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
                pixelated = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)
                out[y1:y2, x1:x2] = pixelated

            elif reg.mode == "solid":
                # Recuadro sólido negro
                out[y1:y2, x1:x2] = 0

        return out
