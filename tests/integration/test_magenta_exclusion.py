"""Prueba de humo de exclusión de captura en Windows (Prueba del Magenta)."""

import sys

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from recordme.capture.factory import create_capture_backend
from recordme.platform_services.factory import get_platform_services
from recordme.utils.geometry import Rect


class MagentaWindow(QWidget):
    """Ventana de prueba pintada con magenta puro (RGB 255, 0, 255 / BGR 255, 0, 255)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.resize(200, 200)
        self.move(100, 100)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(255, 0, 255))


@pytest.mark.skipif(sys.platform != "win32", reason="Prueba específica de Windows DWM / DXGI")
def test_magenta_exclusion_from_capture(qtbot: QtBot) -> None:
    """Verifica que una ventana con SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) no sea capturada."""
    platform_services = get_platform_services()

    window = MagentaWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    # Aplicar exclusión de captura
    excluded = platform_services.exclude_window_from_capture(window)
    assert excluded is True, "No se pudo aplicar SetWindowDisplayAffinity en Windows"

    # Capturar la región de la ventana
    region = Rect(100, 100, 200, 200).to_even()
    backend = create_capture_backend()
    started = backend.start(region, fps=30)
    assert started is True

    import time
    time.sleep(0.3)

    frame = None
    for _ in range(10):
        frame = backend.get_latest_frame()
        if frame is not None:
            break
        time.sleep(0.05)

    backend.stop()

    if frame is not None:
        # En BGR, Magenta es B=255, G=0, R=255
        # Comprobar si hay píxeles magenta (R > 240, B > 240, G < 15)
        blue = frame[:, :, 0]
        green = frame[:, :, 1]
        red = frame[:, :, 2]
        magenta_mask = (red > 240) & (blue > 240) & (green < 20)
        magenta_pixel_count = int(np.sum(magenta_mask))

        assert magenta_pixel_count == 0, f"Se detectaron {magenta_pixel_count} píxeles magenta en la captura excluida!"
