"""Pruebas de interfaz para el widget y editor de teleprompter."""

from pytestqt.qtbot import QtBot

from recordme.config.settings import TeleprompterSettings
from recordme.ui.teleprompter import TeleprompterWidget
from recordme.ui.teleprompter_editor import TeleprompterEditorDialog


def test_teleprompter_widget_lifecycle(qtbot: QtBot) -> None:
    """Verifica que el widget se inicialice, tenga barra de controles y gestione scroll."""
    settings = TeleprompterSettings(font_size=24, seconds_per_line=3.0, lines_visible=2)
    sample_text = (
        "Hola a todos y bienvenidos a esta clase.\n"
        "Hoy vamos a explicar cómo utilizar RecordMe de manera profesional y fluida.\n"
        "El teleprompter permite mantener la mirada en la cámara de forma natural."
    )
    widget = TeleprompterWidget(text=sample_text, settings=settings)
    qtbot.addWidget(widget)
    widget.show()

    assert widget.isVisible()
    assert len(widget._lines) >= 3

    # Botones integrados
    assert widget.btn_play_pause.text() == "▶ Iniciar"
    assert widget.btn_rewind.isVisible() is True

    # Iniciar scroll
    widget.start_scrolling()
    assert widget._is_scrolling is True
    assert widget._is_paused is False
    assert widget.btn_play_pause.text() == "⏸ Pausar"

    # Pausar
    widget.pause_scrolling()
    assert widget._is_paused is True
    assert widget.btn_play_pause.text() == "▶ Reanudar"

    # Reanudar
    widget.resume_scrolling()
    assert widget._is_paused is False
    assert widget.btn_play_pause.text() == "⏸ Pausar"


def test_teleprompter_editor_dialog(qtbot: QtBot) -> None:
    """Verifica el editor de guion, conteo de palabras y alternancia de prueba."""
    settings = TeleprompterSettings(seconds_per_line=3.5)
    dialog = TeleprompterEditorDialog("Primera palabra segunda palabra tercera", settings)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.isVisible()
    assert dialog.windowTitle() == "Teleprompter — RecordMe"
    assert "5 palabras" in dialog.stats_label.text()

    # Modificar texto
    dialog.text_edit.setPlainText("Una dos tres cuatro seis.")
    assert "5 palabras" in dialog.stats_label.text()

    # Probar inicio de prueba in situ (dentro del panel)
    assert "Probar" in dialog.btn_test.text()
    dialog._toggle_in_panel_test()
    assert dialog._is_testing is True
    assert "Detener" in dialog.btn_test.text()

    # Detener prueba in situ
    dialog._toggle_in_panel_test()
    assert dialog._is_testing is False
    assert "Probar" in dialog.btn_test.text()

    # Probar obtención de ajustes
    new_settings = dialog.get_current_settings()
    assert new_settings.seconds_per_line == 3.5
    assert "seis" in new_settings.last_script


def test_teleprompter_font_slider_continuous(qtbot: QtBot) -> None:
    """Verifica que el slider de fuente sea continuo de 16 a 50 con paso de 1 en 1."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QMouseEvent

    from recordme.ui.teleprompter_editor import ContinuousValueSlider

    slider = ContinuousValueSlider(16, 50)
    qtbot.addWidget(slider)
    slider.resize(340, 30)
    slider.show()

    assert slider.minimum() == 16
    assert slider.maximum() == 50
    assert slider.singleStep() == 1

    # Clic a mitad del slider (debe colocarse en torno a 33 px)
    mid_x = slider.width() / 2.0
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(int(mid_x), 15),
        QPoint(int(mid_x), 15),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    slider.mousePressEvent(press_event)
    assert 32 <= slider.value() <= 34

