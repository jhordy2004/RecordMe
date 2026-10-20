"""Pruebas unitarias para la capa de composición de cámara."""

import numpy as np

from recordme.compose.camera_layer import CameraLayer
from recordme.core.render_state import CameraLayout


def test_camera_layer_disabled() -> None:
    """Verifica que si la cámara está deshabilitada el frame base no se modifique."""
    layer = CameraLayer()
    base_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cam_frame = np.full((720, 1280, 3), 255, dtype=np.uint8)
    layout = CameraLayout(enabled=False)

    result = layer.render(base_frame, cam_frame, layout)
    assert np.array_equal(result, base_frame)
    assert np.all(result == 0)


def test_camera_layer_render_circle() -> None:
    """Verifica que la cámara circular se superponga sobre el frame base."""
    layer = CameraLayer()
    base_frame = np.zeros((600, 800, 3), dtype=np.uint8)
    # Cámara roja (BGR: 0, 0, 255)
    cam_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cam_frame[:, :, 2] = 255  # Rojo

    layout = CameraLayout(
        enabled=True,
        shape="circle",
        center_norm_x=0.5,
        center_norm_y=0.5,
        size_pct=25,
        border_enabled=False,
    )

    result = layer.render(base_frame.copy(), cam_frame, layout)

    # El centro debe tener color rojo de la cámara
    center_color = result[300, 400]
    assert center_color[2] > 200, "El centro del círculo debe contener el color de la cámara"

    # Las esquinas lejanas deben seguir siendo negras
    assert result[10, 10, 2] == 0
    assert result[590, 790, 2] == 0


def test_camera_layer_shapes() -> None:
    """Verifica que todas las formas soportadas se rendericen sin excepciones."""
    layer = CameraLayer()
    base_frame = np.zeros((400, 400, 3), dtype=np.uint8)
    cam_frame = np.full((400, 400, 3), 128, dtype=np.uint8)

    for shape in ("circle", "rounded_rect", "rect"):
        layout = CameraLayout(enabled=True, shape=shape, center_norm_x=0.5, center_norm_y=0.5, size_pct=30)
        res = layer.render(base_frame.copy(), cam_frame, layout)
        assert res.shape == (400, 400, 3)
        assert np.any(res > 0)
