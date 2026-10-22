"""Pruebas unitarias para CameraSettingsDialog."""

from pytestqt.qtbot import QtBot

from recordme.config.settings import CameraSettings
from recordme.ui.camera_settings_dialog import CameraSettingsDialog


def test_camera_settings_dialog_defaults(qtbot: QtBot) -> None:
    """Verifica que el diálogo cargue los ajustes por defecto y emita la configuración correcta."""
    settings = CameraSettings()
    dialog = CameraSettingsDialog(current_settings=settings)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.windowTitle() == "Cámara — RecordMe"
    assert dialog.combo_shape.currentData() == "rect"
    assert dialog.spin_width.value() == 230
    assert dialog.spin_height.value() == 120
    assert dialog._bg_image_path is None

    # Probar cambio a forma circular y nombre de expositor
    dialog.combo_shape.setCurrentIndex(1)
    dialog.edit_name.setText("Carlos Developer")

    with qtbot.waitSignal(dialog.settings_applied) as blocker:
        dialog._on_accept()

    saved_settings: CameraSettings = blocker.args[0]
    assert saved_settings.shape == "circle"
    assert saved_settings.name.enabled is True
    assert saved_settings.name.text == "Carlos Developer"
    assert saved_settings.border.enabled is False


def test_camera_settings_dialog_excluded_from_capture(qtbot: QtBot, monkeypatch) -> None:
    """Verifica que CameraSettingsDialog invoque la exclusión de captura al mostrarse."""
    excluded_widgets = []
    from recordme.platform_services.windows import WindowsPlatformServices

    monkeypatch.setattr(WindowsPlatformServices, "exclude_window_from_capture", lambda self, w: excluded_widgets.append(w))

    settings = CameraSettings()
    dialog = CameraSettingsDialog(current_settings=settings)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog in excluded_widgets


def test_controller_set_camera_disabled_stops_source_during_recording() -> None:
    """Verifica que desactivar la cámara durante la grabación detenga y limpie CameraSource para apagar el LED."""
    from recordme.config.settings import AppSettings
    from recordme.core.events import SessionState
    from recordme.core.recording_controller import RecordingController
    from recordme.core.session import SessionManager

    session_manager = SessionManager()
    settings = AppSettings()
    controller = RecordingController(session_manager, settings)

    # Simular una cámara activa con un mock de stop
    class DummyCameraSource:
        stopped = False

        def stop(self):
            self.stopped = True

    dummy_cam = DummyCameraSource()
    controller._camera_source = dummy_cam
    session_manager.transition_to(SessionState.RECORDING)

    # Desactivar cámara estando en RECORDING
    controller.set_camera_enabled(False)

    assert dummy_cam.stopped is True
    assert controller._camera_source is None
    assert controller.camera_layout.enabled is False


def test_camera_settings_dialog_ignores_key_c(qtbot: QtBot) -> None:
    """Verifica que presionar la tecla C repetidamente no cambie la forma de rectangular a circular."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    settings = CameraSettings()
    dialog = CameraSettingsDialog(current_settings=settings)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.combo_shape.currentData() == "rect"

    # Enviar múltiples pulsaciones de la tecla C directamente al combo_shape y al diálogo
    for _ in range(5):
        key_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.NoModifier, "c")
        QApplication.sendEvent(dialog.combo_shape, key_event)
        QApplication.sendEvent(dialog, key_event)
        dialog.combo_shape.keyPressEvent(key_event)
        dialog.keyPressEvent(key_event)

    # Debe permanecer en "rect" sin cambiar a "circle"
    assert dialog.combo_shape.currentData() == "rect"


def test_camera_settings_dialog_allows_key_c_in_name_field(qtbot: QtBot) -> None:
    """Verifica que escribir 'c' en el campo de texto del nombre sí funcione normalmente."""
    settings = CameraSettings()
    dialog = CameraSettingsDialog(current_settings=settings)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.edit_name.setFocus()
    qtbot.keyClicks(dialog.edit_name, "carlos")
    assert dialog.edit_name.text() == "carlos"
    assert dialog.combo_shape.currentData() == "rect"
