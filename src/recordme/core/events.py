"""Definición de estados y eventos de la sesión de grabación."""

from enum import Enum, auto


class SessionState(Enum):
    """Estados del ciclo de vida de la sesión."""
    IDLE = auto()
    CONFIGURING = auto()
    COUNTDOWN = auto()
    RECORDING = auto()
    PAUSED = auto()
    FINALIZING = auto()
    DONE = auto()
    ERROR = auto()
