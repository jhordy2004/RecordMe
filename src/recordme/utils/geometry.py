"""Utilidades geométricas y de conversión de coordenadas y DPI."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    """Representa un rectángulo geométrico (x, y, ancho, alto)."""
    x: int
    y: int
    width: int
    height: int

    def to_even(self) -> "Rect":
        """Devuelve un rectángulo con ancho y alto redondeados a números pares."""
        w = self.width if self.width % 2 == 0 else self.width - 1
        h = self.height if self.height % 2 == 0 else self.height - 1
        # Asegurar un tamaño mínimo de 2x2
        w = max(2, w)
        h = max(2, h)
        return Rect(x=self.x, y=self.y, width=w, height=h)

    def to_tuple(self) -> tuple[int, int, int, int]:
        """Devuelve (x, y, width, height)."""
        return (self.x, self.y, self.width, self.height)

    def contains(self, px: int, py: int) -> bool:
        """Indica si un punto (px, py) está contenido en el rectángulo."""
        return (self.x <= px < self.x + self.width) and (self.y <= py < self.y + self.height)


def to_physical_pixels(logical_value: int | float, dpr: float) -> int:
    """Convierte un valor de píxeles lógicos a píxeles físicos redondeados."""
    return int(round(logical_value * dpr))


def to_logical_pixels(physical_value: int | float, dpr: float) -> int:
    """Convierte un valor de píxeles físicos a píxeles lógicos redondeados."""
    if dpr == 0:
        return int(physical_value)
    return int(round(physical_value / dpr))


def make_even(value: int) -> int:
    """Asegura que un valor entero sea par truncando el último bit impar si es necesario."""
    return value if value % 2 == 0 else value - 1
