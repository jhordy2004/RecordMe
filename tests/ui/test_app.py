"""Pruebas de interfaz para la barra flotante y la aplicación."""

from pytestqt.qtbot import QtBot

from recordme.app import RecordMeApp
from recordme.config.settings import AppSettings
from recordme.core.events import SessionState
from recordme.core.session import SessionManager
from recordme.ui.toolbar import FloatingToolbar
from recordme.utils.geometry import Rect


def test_floating_toolbar_initial_state(qtbot: QtBot) -> None:
    """Verifica que la barra flotante inicie con los botones correctos."""
    session_manager = SessionManager()
    toolbar = FloatingToolbar(session_manager)
    qtbot.addWidget(toolbar)
    toolbar.show()

    assert toolbar.isVisible()
    assert toolbar.btn_record.text() == "Grabar"
    assert toolbar.btn_area.isVisible() is True
    assert toolbar.btn_pause.isVisible() is False
    assert toolbar.timer_label.isVisible() is False
    assert toolbar.btn_cam.text() == "Cámara: Off"
    assert toolbar.btn_close_app.isVisible() is True
    assert toolbar.btn_censor.isVisible() is True
    assert toolbar.btn_censor.text() == "+ Censurar"
    assert toolbar.zoom_badge.text() == "🔍 100%"

    # Probar actualización de zoom en la barra
    toolbar.update_zoom_display(1.20)
    assert toolbar.zoom_badge.text() == "🔍 120%"
    toolbar.update_zoom_display(1.0)
    assert toolbar.zoom_badge.text() == "🔍 100%"

    # Probar alternancia de cámara
    toolbar.set_camera_enabled(True)
    assert toolbar.btn_cam.text() == "Cámara: On"
    toolbar.set_camera_enabled(False)
    assert toolbar.btn_cam.text() == "Cámara: Off"

    # Probar actualización de región
    toolbar.update_selected_region(Rect(0, 0, 1280, 720))
    assert toolbar.area_label.text() == "1280×720"


def test_toolbar_state_changes(qtbot: QtBot) -> None:
    """Verifica la adaptación de la barra cuando cambia el estado de la sesión."""
    session_manager = SessionManager()
    toolbar = FloatingToolbar(session_manager)
    qtbot.addWidget(toolbar)
    toolbar.show()

    # Transición a RECORDING
    session_manager.transition_to(SessionState.CONFIGURING)
    session_manager.transition_to(SessionState.COUNTDOWN)
    session_manager.transition_to(SessionState.RECORDING)

    assert toolbar.btn_record.text() == "Detener"
    assert toolbar.btn_pause.isVisible() is True
    assert toolbar.btn_pause.text() == "Pausar"
    assert toolbar.timer_label.isVisible() is True
    assert toolbar.btn_area.isVisible() is False

    # Transición a PAUSED
    session_manager.transition_to(SessionState.PAUSED)
    assert toolbar.btn_pause.text() == "Reanudar"

    # Transición a FINALIZING
    session_manager.transition_to(SessionState.FINALIZING)
    assert toolbar.btn_record.text() == "Guardando..."


def test_recordme_app_instantiation(qtbot: QtBot) -> None:
    """Verifica la inicialización del coordinador RecordMeApp."""
    session_manager = SessionManager()
    settings = AppSettings()
    app = RecordMeApp(session_manager, settings)
    qtbot.addWidget(app.toolbar)
    app.show()

    assert app.toolbar.isVisible()
    assert app.controller is not None
    app.hotkey_service.stop()
