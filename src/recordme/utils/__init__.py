"""Utilidades generales de RecordMe."""

from recordme.utils.geometry import Rect, make_even, to_logical_pixels, to_physical_pixels
from recordme.utils.logging_setup import setup_logging

__all__ = [
    "Rect",
    "make_even",
    "setup_logging",
    "to_logical_pixels",
    "to_physical_pixels",
]
