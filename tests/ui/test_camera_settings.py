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
