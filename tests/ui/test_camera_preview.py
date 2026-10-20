"""Pruebas de interfaz para la vista previa de la cámara."""

import numpy as np
from pytestqt.qtbot import QtBot

from recordme.core.render_state import CameraLayout
from recordme.ui.camera_preview import CameraPreviewWidget
from recordme.utils.geometry import Rect


def test_camera_preview_widget(qtbot: QtBot) -> None:
    """Verifica que el widget de preview responda a frames y emita señales de layout."""
    layout = CameraLayout(enabled=True, shape="circle", size_pct=20)
    region = Rect(0, 0, 1280, 720)
    widget = CameraPreviewWidget(layout, region)
    qtbot.addWidget(widget)
    widget.show()

    assert widget.isVisible()

    # Enviar un frame sintético a la vista previa
    frame = np.full((240, 320, 3), 100, dtype=np.uint8)
    widget.update_frame(frame)
    assert widget._current_pixmap is not None
    assert not widget._current_pixmap.isNull()

    # Probar señal al cambiar de región
    layout_events: list[CameraLayout] = []
    widget.layout_updated.connect(lambda lay: layout_events.append(lay))

    widget.update_capture_region(Rect(100, 100, 800, 600))
    assert len(layout_events) == 1
    assert 0.0 <= layout_events[0].center_norm_x <= 1.0
    assert 0.0 <= layout_events[0].center_norm_y <= 1.0
