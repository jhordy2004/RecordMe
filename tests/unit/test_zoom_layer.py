"""Pruebas unitarias para la capa de zoom en vivo y filtro exponencial tau."""

import numpy as np

from recordme.compose.zoom_layer import ZoomLayer


def test_zoom_layer_no_zoom() -> None:
    """Verifica que a 1.0x no se altere el fotograma de entrada."""
    layer = ZoomLayer(tau_seconds=0.20)
    frame = np.full((720, 1280, 3), 100, dtype=np.uint8)

    out = layer.render(frame, target_zoom=1.0, target_cx=0.5, target_cy=0.5, dt=0.033)
    assert np.array_equal(frame, out)
    assert layer.current_zoom <= 1.01


def test_zoom_layer_smooth_convergence() -> None:
    """Verifica la convergencia exponencial temporal hacia el zoom y centro objetivo."""
    layer = ZoomLayer(tau_seconds=0.10)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Paso 1: dt corto (16ms)
    out1 = layer.render(frame, target_zoom=2.0, target_cx=0.8, target_cy=0.2, dt=0.016)
    assert out1.shape == frame.shape
    # Debe haber avanzado pero no haber llegado al 2.0x instantáneamente
    assert 1.0 < layer.current_zoom < 2.0
    assert 0.5 < layer.current_center[0] < 0.8

    # Varios pasos después debe converger muy cerca de 2.0x
    for _ in range(30):
        layer.render(frame, target_zoom=2.0, target_cx=0.8, target_cy=0.2, dt=0.033)

    assert abs(layer.current_zoom - 2.0) < 0.05
    assert abs(layer.current_center[0] - 0.8) < 0.05
    assert abs(layer.current_center[1] - 0.2) < 0.05
