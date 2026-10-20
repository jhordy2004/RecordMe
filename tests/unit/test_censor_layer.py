"""Pruebas unitarias para la capa de censura en tiempo real."""

import numpy as np

from recordme.compose.censor_layer import CensorLayer
from recordme.core.render_state import CensorRegion
from recordme.utils.geometry import Rect


def test_censor_solid_mode() -> None:
    """Verifica que el modo sólido establezca ceros en la región indicada."""
    layer = CensorLayer()
    frame = np.full((400, 600, 3), 200, dtype=np.uint8)
    capture_region = Rect(0, 0, 600, 400)

    region = CensorRegion(
        id="c1",
        rect=Rect(50, 50, 100, 80),
        mode="solid",
        active=True,
    )

    out = layer.render(frame, [region], capture_region)
    # Fuera de la región debe mantener valor original 200
    assert out[10, 10, 0] == 200
    # Dentro de la región (50..150, 50..130) debe ser 0
    assert np.all(out[50:130, 50:150] == 0)


def test_censor_blur_and_pixelate_modes() -> None:
    """Verifica que los modos blur y pixelate modifiquen los valores del área."""
    layer = CensorLayer()
    # Crear un patrón contrastado
    frame = np.zeros((300, 400, 3), dtype=np.uint8)
    frame[:, ::2] = 255
    capture_region = Rect(0, 0, 400, 300)

    reg_blur = CensorRegion(id="b1", rect=Rect(20, 20, 80, 80), mode="blur", blur_strength=25)
    reg_pixel = CensorRegion(id="p1", rect=Rect(150, 20, 80, 80), mode="pixelate", pixel_size=16)

    out = layer.render(frame, [reg_blur, reg_pixel], capture_region)

    # Las regiones modificadas no deben ser idénticas al original con bordes afilados
    assert not np.array_equal(out[20:100, 20:100], frame[20:100, 20:100])
    assert not np.array_equal(out[20:100, 150:230], frame[20:100, 150:230])
    # Fuera debe permanecer intacto
    assert np.array_equal(out[200:250, 200:250], frame[200:250, 200:250])


def test_censor_inactive_or_out_of_bounds() -> None:
    """Verifica que regiones inactivas o fuera de pantalla no afecten el frame."""
    layer = CensorLayer()
    frame = np.full((200, 200, 3), 150, dtype=np.uint8)
    capture_region = Rect(0, 0, 200, 200)

    reg_inactive = CensorRegion(id="i1", rect=Rect(10, 10, 50, 50), mode="solid", active=False)
    reg_oob = CensorRegion(id="o1", rect=Rect(500, 500, 50, 50), mode="solid", active=True)

    out = layer.render(frame, [reg_inactive, reg_oob], capture_region)
    assert np.array_equal(frame, out)
