"""Módulo central de lógica de sesión, renderizado y grabación."""

from recordme.core.events import SessionState
from recordme.core.recording_controller import RecordingController
from recordme.core.render_state import CameraLayout, CensorRegion, RenderState
from recordme.core.session import SessionManager

__all__ = [
    "CameraLayout",
    "CensorRegion",
    "RecordingController",
    "RenderState",
    "SessionManager",
    "SessionState",
]
