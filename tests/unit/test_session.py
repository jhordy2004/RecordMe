"""Pruebas unitarias para la máquina de estados de la sesión."""

from recordme.core.events import SessionState
from recordme.core.session import SessionManager


def test_session_initial_state() -> None:
    """Verifica el estado inicial de la sesión."""
    sm = SessionManager()
    assert sm.state == SessionState.IDLE


def test_valid_transitions() -> None:
    """Verifica transiciones de estado legales."""
    sm = SessionManager()
    events: list[tuple[SessionState, SessionState]] = []

    def on_change(old_state: SessionState, new_state: SessionState) -> None:
        events.append((old_state, new_state))

    sm.add_listener(on_change)

    # Flujo normal de grabación
    assert sm.transition_to(SessionState.CONFIGURING) is True
    assert sm.transition_to(SessionState.COUNTDOWN) is True
    assert sm.transition_to(SessionState.RECORDING) is True
    assert sm.transition_to(SessionState.PAUSED) is True
    assert sm.transition_to(SessionState.RECORDING) is True
    assert sm.transition_to(SessionState.FINALIZING) is True
    assert sm.transition_to(SessionState.DONE) is True
    assert sm.transition_to(SessionState.IDLE) is True

    assert len(events) == 8
    assert events[0] == (SessionState.IDLE, SessionState.CONFIGURING)
    assert events[-1] == (SessionState.DONE, SessionState.IDLE)


def test_invalid_transitions() -> None:
    """Verifica que las transiciones no permitidas sean rechazadas."""
    sm = SessionManager()
    # No se puede saltar de IDLE a RECORDING directamente
    assert sm.transition_to(SessionState.RECORDING) is False
    assert sm.state == SessionState.IDLE


def test_error_transition() -> None:
    """Verifica que cualquier estado pueda transicionar a ERROR."""
    sm = SessionManager()
    sm.transition_to(SessionState.CONFIGURING)
    assert sm.transition_to(SessionState.ERROR, error_message="Fallo de hardware") is True
    assert sm.state == SessionState.ERROR
    assert sm.last_error == "Fallo de hardware"

    # Desde ERROR solo se puede volver a IDLE
    assert sm.transition_to(SessionState.RECORDING) is False
    assert sm.transition_to(SessionState.IDLE) is True
    assert sm.state.name == "IDLE"
    assert sm.last_error is None
