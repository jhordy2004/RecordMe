"""Pruebas de interfaz para el diálogo de configuración de audio y loopback del sistema."""

from pytestqt.qtbot import QtBot

from recordme.config.settings import AudioSettings
from recordme.core.session import SessionManager
from recordme.ui.audio_settings_dialog import AudioSettingsDialog
from recordme.ui.toolbar import FloatingToolbar


def test_audio_settings_dialog_defaults_and_mode_selection(qtbot: QtBot) -> None:
    """Verifica que el diálogo de audio cargue opciones por defecto y permita alternar entre mic y mic+sistema."""
    settings = AudioSettings(
        mode="mic_only",
        noise_reduction=True,
        mic_gain_db=0.0,
    )
    dialog = AudioSettingsDialog(current_settings=settings)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.isVisible()
    # Por defecto, la opción de solo audio de entrada (micrófono) está seleccionada
    assert dialog.radio_mic_only.isChecked() is True
    assert dialog.radio_mic_and_sys.isChecked() is False

    # Supresión de ruido inteligente debe estar activa por defecto
    assert dialog.check_noise.isChecked() is True

    # Cambiar a Micrófono + Audio del Sistema (Loopback)
    dialog.radio_mic_and_sys.setChecked(True)
    assert dialog.radio_mic_and_sys.isChecked() is True

    # Guardar
    emitted_settings: list[AudioSettings] = []
    dialog.settings_applied.connect(emitted_settings.append)
    dialog._on_save_clicked()

    assert len(emitted_settings) == 1
    saved = emitted_settings[0]
    assert saved.mode == "mic_and_system"
    assert saved.system_audio_enabled is True
    assert saved.noise_reduction is True


def test_toolbar_mic_button_vs_shortcut_m(qtbot: QtBot) -> None:
    """Verifica que hacer clic en el botón de micrófono solicite el panel de ajustes,

    mientras que el atajo M / Alt+M únicamente mutea/desmutea sin abrir el panel.
    """
    session_manager = SessionManager()
    toolbar = FloatingToolbar(session_manager)
    qtbot.addWidget(toolbar)
    toolbar.show()

    settings_requested = False
    toolbar.mic_settings_requested.connect(lambda: globals().update(settings_requested=True))

    def on_settings():
        nonlocal settings_requested
        settings_requested = True

    toolbar.mic_settings_requested.connect(on_settings)

    # 1. Simular clic en btn_mic: debe solicitar abrir el panel de configuración
    toolbar.btn_mic.click()
    assert settings_requested is True

    # Resetear flag
    settings_requested = False

    # 2. Simular atajo M (toggle_mic_mute): debe cambiar estado SIN abrir panel
    initial_mic_state = toolbar._mic_enabled
    toolbar.toggle_mic_mute()
    assert toolbar._mic_enabled == (not initial_mic_state)
    assert settings_requested is False  # NO debe solicitar abrir el panel de configuración


def test_toolbar_logo_and_zoom_label(qtbot: QtBot) -> None:
    """Verifica que la barra contenga el logo en lugar del texto 'RecordMe' y que el zoom use 'Ctrl +, Ctrl -'."""
    session_manager = SessionManager()
    toolbar = FloatingToolbar(session_manager)
    qtbot.addWidget(toolbar)
    toolbar.show()

    # 1. El widget del logo debe tener un QPixmap cargado en su tamaño real (114x38 px)
    assert toolbar.app_logo.pixmap() is not None
    assert not toolbar.app_logo.pixmap().isNull()
    assert toolbar.app_logo.pixmap().width() == 114
    assert toolbar.app_logo.pixmap().height() == 38
    # No debe tener texto "RecordMe" cuando el pixmap está cargado
    assert toolbar.app_logo.text() == ""

    # 2. El badge de atajo de zoom debe ser 'Alt +, Alt -'
    toolbar._show_badge_for(toolbar.zoom_badge)
    assert toolbar._hover_badge.isVisible() is True
    assert toolbar._hover_badge._key_badge.text() == "Alt +, Alt -"


def test_audio_settings_dialog_dual_source_level_meter(qtbot: QtBot) -> None:
    """Verifica que el medidor de nivel VU soporte audio del sistema y micrófono simultáneamente."""
    settings = AudioSettings(mode="mic_and_system", noise_reduction=True)
    dialog = AudioSettingsDialog(current_settings=settings)
    qtbot.addWidget(dialog)
    dialog.show()

    # Debe haber iniciado timer y monitor
    assert dialog._monitor_active is True
    assert dialog._meter_timer.isActive() is True

    # Simular niveles detectados en tiempo real
    dialog._mic_level = 0.35
    dialog._sys_level = 0.72
    dialog._on_meter_tick()
    # En modo mic_and_system, el nivel combinado debe reflejar el pico máximo (0.72)
    assert dialog.level_meter._level == 0.72

    # Cambiar a modo mic_only: debe ignorar el audio del sistema
    dialog.radio_mic_only.setChecked(True)
    dialog._mic_level = 0.35
    dialog._on_meter_tick()
    assert dialog.level_meter._level == 0.35

    # Al cerrar el diálogo, debe detenerse el timer y resetear el nivel a 0.0
    dialog.reject()
    assert dialog._monitor_active is False
    assert dialog._meter_timer.isActive() is False
    assert dialog.level_meter._level == 0.0
