"""Utilidades generales de RecordMe."""

from recordme.utils.geometry import (
    Rect,
    get_primary_screen_physical_rect,
    make_even,
    to_logical_pixels,
    to_physical_pixels,
)
from recordme.utils.logging_setup import setup_logging

__all__ = [
    "Rect",
    "get_primary_screen_physical_rect",
    "make_even",
    "setup_logging",
    "to_logical_pixels",
    "to_physical_pixels",
]
