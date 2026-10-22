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
    assert toolbar.btn_mic.text() == "Micrófono: On"
    assert toolbar.btn_cam.text() == "Cámara: Off"
    assert toolbar.btn_close_app.isVisible() is True
    assert toolbar.btn_censor.isVisible() is True
    assert toolbar.btn_censor.text() == "+ Censurar"
    assert toolbar.zoom_badge.text() == "🔍 100%"

    # Tooltips nativos inferiores deben estar vacíos para que solo aparezca el badge superior
    assert toolbar.btn_area.toolTip() == ""
    assert toolbar.btn_record.toolTip() == ""
    assert toolbar.btn_mic.toolTip() == ""
    assert toolbar.btn_cam.toolTip() == ""
    assert toolbar.btn_teleprompter.toolTip() == ""
    assert toolbar.btn_censor.toolTip() == ""
    assert toolbar.btn_close_app.toolTip() == ""

    # Probar alternancia de micrófono (On -> Off -> On)
    toolbar._toggle_mic()
    assert toolbar.btn_mic.text() == "Micrófono: Off"
    toolbar._toggle_mic()
    assert toolbar.btn_mic.text() == "Micrófono: On"

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

    # Transición a COUNTDOWN (debe tener ya los botones Pausar y Detener habilitados)
    session_manager.transition_to(SessionState.CONFIGURING)
    session_manager.transition_to(SessionState.COUNTDOWN)
    assert toolbar.btn_record.text() == "Detener"
    assert toolbar.btn_record.isEnabled() is True
    assert toolbar.btn_pause.isVisible() is True
    assert toolbar.btn_pause.isEnabled() is True

    # Transición a RECORDING
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
    app.screen_zoom_overlay.close()


def test_toolbar_hover_badge_display(qtbot: QtBot) -> None:
    """Verifica que el hover badge de alto contraste se active y muestre texto y atajos al pasar el cursor."""
    session_manager = SessionManager()
    toolbar = FloatingToolbar(session_manager)
    qtbot.addWidget(toolbar)
    toolbar.show()

    # 1. Simular hover sobre btn_area
    toolbar._show_badge_for(toolbar.btn_area)
    assert toolbar._hover_badge.isVisible() is True
    assert toolbar._hover_badge._action_label.text() == "Atajo"
    assert toolbar._hover_badge._key_badge.text() == "Alt+L / L"

    # 2. Simular hover sobre btn_record
    toolbar._show_badge_for(toolbar.btn_record)
    assert toolbar._hover_badge.isVisible() is True
    assert toolbar._hover_badge._action_label.text() == "Atajo"
    assert toolbar._hover_badge._key_badge.text() == "Alt+R / R"

    # 3. Ocultar badge
    toolbar._hover_badge.hide_badge()
    assert toolbar._hover_badge.isVisible() is False


def test_on_recording_finished_save_as(qtbot: QtBot, tmp_path, monkeypatch) -> None:
    """Verifica que el diálogo Guardar Como mueva el archivo al nombre y ruta elegidos por el usuario."""
    from PySide6.QtWidgets import QFileDialog

    session_manager = SessionManager()
    settings = AppSettings()
    app = RecordMeApp(session_manager, settings)
    qtbot.addWidget(app.toolbar)

    # Crear archivo origen simulado
    source_file = tmp_path / "temp_Grabacion.mp4"
    source_file.write_text("dummy video content")

    # Destino personalizado elegido por el usuario
    custom_dest = tmp_path / "custom_folder" / "MiVideoFinal.mp4"

    # Mockear QFileDialog.getSaveFileName para simular que el usuario eligió custom_dest
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(custom_dest), "MP4 Video (*.mp4)"),
    )

    session_manager.transition_to(SessionState.DONE)
    app._on_recording_finished(source_file)

    assert custom_dest.exists()
    assert custom_dest.read_text() == "dummy video content"
    assert not source_file.exists()
    assert session_manager.state == SessionState.IDLE

    app.hotkey_service.stop()
    app.screen_zoom_overlay.close()


def test_region_selector_reopen_after_escape(qtbot: QtBot) -> None:
    """Verifica que tras cancelar con Esc o clic derecho, se pueda volver a abrir con el atajo L o el botón."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QKeyEvent, QMouseEvent

    session_manager = SessionManager()
    settings = AppSettings()
    app = RecordMeApp(session_manager, settings)
    qtbot.addWidget(app.toolbar)

    # 1. Abrir selector de área por primera vez vía señal de atajo
    app.hotkey_service.trigger_area.emit()
    assert app.selector_overlay is not None
    qtbot.addWidget(app.selector_overlay)

    # 2. Cancelar con tecla Escape
    esc_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    app.selector_overlay.keyPressEvent(esc_event)

    # Debe quedar limpio (None) tras cancelar
    assert app.selector_overlay is None

    # 3. Volver a abrir el selector de área vía señal de atajo L -> Debe abrir correctamente
    app.hotkey_service.trigger_area.emit()
    assert app.selector_overlay is not None
    qtbot.addWidget(app.selector_overlay)

    # 4. Cancelar con clic derecho
    right_click = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(100, 100),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    app.selector_overlay.mousePressEvent(right_click)
    assert app.selector_overlay is None

    # 5. Volver a abrir el selector de área haciendo clic en el botón de la barra -> Debe abrir correctamente
    app.toolbar.btn_area.click()
    assert app.selector_overlay is not None
    qtbot.addWidget(app.selector_overlay)
    app.selector_overlay.close()
    assert app.selector_overlay is None

    app.hotkey_service.stop()
    app.screen_zoom_overlay.close()


def test_hotkey_suppression_when_text_input_focused(qtbot: QtBot, monkeypatch) -> None:
    """Verifica que las teclas directas (R, P, L, etc.) se ignoren cuando el usuario escribe, pero Alt+Key funcione."""
    from pynput.keyboard import Key, KeyCode

    from recordme.platform_services.hotkeys import GlobalHotkeyService

    hotkeys = GlobalHotkeyService()
    # Simular que el usuario tiene un campo de texto enfocado en el sistema
    monkeypatch.setattr(hotkeys, "_is_text_input_active_system_wide", lambda: True)

    fired_actions: list[str] = []
    hotkeys.trigger_record.connect(lambda: fired_actions.append("record"))
    hotkeys.trigger_area.connect(lambda: fired_actions.append("area"))
    hotkeys.trigger_pause.connect(lambda: fired_actions.append("pause"))

    # Simular presionar 'r', 'l', 'p' directos (sin Alt)
    hotkeys._on_press(KeyCode.from_char("r"))
    hotkeys._on_press(KeyCode.from_char("l"))
    hotkeys._on_press(KeyCode.from_char("p"))

    # Ninguna acción directa debe dispararse mientras escribe
    assert len(fired_actions) == 0

    # Sin embargo, combinaciones con Alt explícitas deben funcionar incluso si está en un campo de texto
    monkeypatch.setattr(hotkeys, "_is_alt_pressed", lambda: True)
    hotkeys._on_press(KeyCode.from_char("r"))
    assert "record" in fired_actions
    hotkeys._on_press(KeyCode.from_char("l"))
    assert "area" in fired_actions
    hotkeys._on_press(KeyCode.from_char("p"))
    assert "pause" in fired_actions

    # Ahora simular que el usuario NO está en un campo de texto y suelta Alt
    monkeypatch.setattr(hotkeys, "_is_alt_pressed", lambda: False)
    monkeypatch.setattr(hotkeys, "_is_text_input_active_system_wide", lambda: False)
    fired_actions.clear()
    hotkeys._last_trigger_time.clear()

    hotkeys._on_press(KeyCode.from_char("r"))
    assert "record" in fired_actions


def test_escape_clears_selected_area_and_resets_fullscreen(qtbot: QtBot) -> None:
    """Verifica que al presionar Esc con un área seleccionada, se elimine la selección y vuelva a pantalla completa."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    from recordme.utils.geometry import Rect, get_primary_screen_physical_rect

    session_manager = SessionManager()
    settings = AppSettings()
    app = RecordMeApp(session_manager, settings)
    qtbot.addWidget(app.toolbar)
    app.show()

    # 1. Definir un área personalizada (menor que pantalla completa)
    custom_region = Rect(100, 100, 400, 300)
    app._on_region_selected(custom_region)
    assert app.region_frame is not None
    assert app.region_frame.isVisible() is True
    qtbot.addWidget(app.region_frame)

    # 2. Presionar Esc globalmente -> Debe eliminar el área y restablecer a pantalla completa
    app._on_escape_pressed()
    assert app.region_frame is None
    screen_rect = get_primary_screen_physical_rect()
    assert app.controller.current_region == screen_rect

    # 3. Volver a definir un área y presionar Esc en el marco directamente
    app._on_region_selected(custom_region)
    assert app.region_frame is not None
    qtbot.addWidget(app.region_frame)

    esc_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    app.region_frame.keyPressEvent(esc_event)
    assert app.region_frame is None
    assert app.controller.current_region == screen_rect

    app.hotkey_service.stop()
    app.screen_zoom_overlay.close()


def test_toolbar_buttons_do_not_shrink_on_recording(qtbot: QtBot) -> None:
    """Verifica que al iniciar grabación y aparecer el botón de pausa, los botones no se achiquen."""
    session_manager = SessionManager()
    toolbar = FloatingToolbar(session_manager)
    qtbot.addWidget(toolbar)
    toolbar.show()

    # Guardar anchos iniciales en IDLE
    idle_mic_w = toolbar.btn_mic.width()
    idle_cam_w = toolbar.btn_cam.width()
    idle_tele_w = toolbar.btn_teleprompter.width()
    idle_censor_w = toolbar.btn_censor.width()

    # Transición a COUNTDOWN y RECORDING
    session_manager.transition_to(SessionState.CONFIGURING)
    session_manager.transition_to(SessionState.COUNTDOWN)
    session_manager.transition_to(SessionState.RECORDING)

    assert toolbar.btn_pause.isVisible() is True

    # Los anchos de los botones no deben haberse reducido
    assert toolbar.btn_mic.width() >= idle_mic_w
    assert toolbar.btn_cam.width() >= idle_cam_w
    assert toolbar.btn_teleprompter.width() >= idle_tele_w
    assert toolbar.btn_censor.width() >= idle_censor_w
