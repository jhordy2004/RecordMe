"""Módulo central de lógica de sesión y renderizado."""

from recordme.core.events import SessionState
from recordme.core.render_state import CameraLayout, CensorRegion, RenderState
from recordme.core.session import SessionManager

__all__ = [
    "CameraLayout",
    "CensorRegion",
    "RenderState",
    "SessionManager",
    "SessionState",
]
