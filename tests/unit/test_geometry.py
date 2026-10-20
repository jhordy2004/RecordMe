"""Pruebas unitarias para utilidades geométricas."""

from recordme.utils.geometry import (
    Rect,
    make_even,
    to_logical_pixels,
    to_physical_pixels,
)


def test_rect_to_even() -> None:
    """Verifica que las dimensiones del rectángulo siempre se alineen a números pares."""
    rect = Rect(x=10, y=20, width=1921, height=1079)
    even_rect = rect.to_even()
    assert even_rect.x == 10
    assert even_rect.y == 20
    assert even_rect.width == 1920
    assert even_rect.height == 1078
    assert even_rect.width % 2 == 0
    assert even_rect.height % 2 == 0


def test_rect_contains() -> None:
    """Verifica la detección de contención de puntos en el rectángulo."""
    rect = Rect(x=100, y=100, width=200, height=150)
    assert rect.contains(100, 100) is True
    assert rect.contains(299, 249) is True
    assert rect.contains(300, 250) is False
    assert rect.contains(50, 50) is False


def test_make_even() -> None:
    """Verifica la función make_even."""
    assert make_even(1080) == 1080
    assert make_even(1081) == 1080
    assert make_even(0) == 0


def test_dpi_conversion() -> None:
    """Verifica la conversión entre píxeles físicos y lógicos con diferentes DPR."""
    # DPR 1.25 (125% escala Windows)
    physical = to_physical_pixels(100, 1.25)
    assert physical == 125

    logical = to_logical_pixels(125, 1.25)
    assert logical == 100
