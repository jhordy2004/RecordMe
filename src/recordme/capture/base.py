"""Protocolo base para backends de captura de pantalla."""

from typing import Protocol

import numpy as np
import numpy.typing as npt

from recordme.utils.geometry import Rect


class CaptureBackend(Protocol):
    """Protocolo abstracto que deben implementar los backends de captura de pantalla."""

    def start(self, region: Rect, fps: int = 30) -> bool:
        """Inicia la captura en la región y a los FPS especificados."""
        ...

    def get_latest_frame(self) -> npt.NDArray[np.uint8] | None:
        """Devuelve el frame más reciente capturado en formato BGR o RGB (uint8), o None si no hay nuevo frame."""
        ...

    def stop(self) -> None:
        """Detiene la captura y libera recursos asociados."""
        ...

    def screens(self) -> list[Rect]:
        """Devuelve la lista de rectángulos de los monitores disponibles en coordenadas físicas."""
        ...
