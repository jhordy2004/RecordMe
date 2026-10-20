"""Pruebas unitarias para el compositor de video y preservación exacta de regiones."""

from unittest.mock import MagicMock

import numpy as np

from recordme.compose.compositor import Compositor
from recordme.core.render_state import CameraLayout, RenderState
from recordme.encode.video_writer import VideoWriter
from recordme.utils.geometry import Rect


def test_compositor_already_cropped_region_preserved() -> None:
    """Verifica que si el backend entrega un frame ya recortado a la región, no se recorte nuevamente."""
    region = Rect(x=300, y=150, width=500, height=400)
    render_state = RenderState(
        capture_region=region,
        output_width=500,
        output_height=400,
        camera=CameraLayout(enabled=False),
    )

    mock_backend = MagicMock()
    # Backend entrega frame de 500x400 (ya recortado con región)
    raw = np.full((400, 500, 3), 128, dtype=np.uint8)
    mock_backend.get_latest_frame.return_value = raw

    mock_writer = MagicMock(spec=VideoWriter)

    compositor = Compositor(
        capture_backend=mock_backend,
        video_writer=mock_writer,
        initial_render_state=render_state,
        fps=30,
    )

    composed = compositor._compose_frame()
    assert composed is not None
    assert composed.shape == (400, 500, 3)
    # Debe ser idéntico sin recortes secundarios
    assert np.array_equal(composed, raw)


def test_compositor_fullscreen_frame_cropped_to_region() -> None:
    """Verifica que si el backend entrega la pantalla completa, el compositor recorte la región con offset."""
    region = Rect(x=100, y=50, width=200, height=150)
    render_state = RenderState(
        capture_region=region,
        output_width=200,
        output_height=150,
        camera=CameraLayout(enabled=False),
    )

    mock_backend = MagicMock()
    # Frame de pantalla completa 1366x768
    full_screen = np.zeros((768, 1366, 3), dtype=np.uint8)
    # Marcar la región con un valor único
    full_screen[50:200, 100:300] = 255
    mock_backend.get_latest_frame.return_value = full_screen

    mock_writer = MagicMock(spec=VideoWriter)

    compositor = Compositor(
        capture_backend=mock_backend,
        video_writer=mock_writer,
        initial_render_state=render_state,
        fps=30,
    )

    composed = compositor._compose_frame()
    assert composed is not None
    assert composed.shape == (150, 200, 3)
    assert np.all(composed == 255)
