"""Controlador de máquina de estados de la sesión."""

import logging
import threading
from collections.abc import Callable

from recordme.core.events import SessionState

logger = logging.getLogger(__name__)

# Transiciones de estado permitidas
VALID_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.IDLE: {SessionState.CONFIGURING, SessionState.COUNTDOWN, SessionState.ERROR},
    SessionState.CONFIGURING: {
        SessionState.COUNTDOWN,
        SessionState.RECORDING,
        SessionState.IDLE,
        SessionState.ERROR,
    },
    SessionState.COUNTDOWN: {SessionState.RECORDING, SessionState.IDLE, SessionState.ERROR},
    SessionState.RECORDING: {
        SessionState.PAUSED,
        SessionState.FINALIZING,
        SessionState.IDLE,
        SessionState.ERROR,
    },
    SessionState.PAUSED: {
        SessionState.RECORDING,
        SessionState.FINALIZING,
        SessionState.IDLE,
        SessionState.ERROR,
    },
    SessionState.FINALIZING: {SessionState.DONE, SessionState.ERROR},
    SessionState.DONE: {
        SessionState.IDLE,
        SessionState.CONFIGURING,
        SessionState.RECORDING,
        SessionState.ERROR,
    },
    SessionState.ERROR: {SessionState.IDLE},
}


class SessionManager:
    """Administra el estado de la sesión de grabación y notifica a los suscriptores."""

    def __init__(self) -> None:
        self._state: SessionState = SessionState.IDLE
        self._listeners: list[Callable[[SessionState, SessionState], None]] = []
        self._last_error_message: str | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> SessionState:
        """Estado actual de la sesión."""
        with self._lock:
            return self._state

    @property
    def last_error(self) -> str | None:
        """Último mensaje de error si el estado es ERROR."""
        with self._lock:
            return self._last_error_message

    def add_listener(self, listener: Callable[[SessionState, SessionState], None]) -> None:
        """Agrega un callback que recibe (estado_anterior, nuevo_estado)."""
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[SessionState, SessionState], None]) -> None:
        """Elimina un callback previamente registrado."""
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def transition_to(self, new_state: SessionState, error_message: str | None = None) -> bool:
        """Intenta transicionar a un nuevo estado si la regla lo permite."""
        with self._lock:
            if new_state == self._state:
                return True

            allowed = VALID_TRANSITIONS.get(self._state, set())
            if new_state not in allowed:
                logger.warning(
                    "Transición de estado inválida: %s -> %s (permitidas: %s)",
                    self._state.name,
                    new_state.name,
                    [s.name for s in allowed],
                )
                return False

            old_state = self._state
            self._state = new_state
            if new_state == SessionState.ERROR:
                self._last_error_message = error_message
                logger.error("Sesión entró en estado ERROR: %s", error_message)
            elif old_state == SessionState.ERROR:
                self._last_error_message = None

            logger.info("Transición de sesión: %s -> %s", old_state.name, new_state.name)
            listeners_snapshot = list(self._listeners)

        # Notificar a los observadores de manera segura fuera del lock
        for listener in listeners_snapshot:
            try:
                listener(old_state, new_state)
            except Exception as e:
                logger.exception("Error en listener de transición de estado: %s", e)

        return True
