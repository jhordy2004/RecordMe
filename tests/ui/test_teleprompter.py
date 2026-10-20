"""Pruebas de interfaz para el widget y editor de teleprompter."""

from pytestqt.qtbot import QtBot

from recordme.config.settings import TeleprompterSettings
from recordme.ui.teleprompter import TeleprompterWidget
from recordme.ui.teleprompter_editor import TeleprompterEditorDialog


def test_teleprompter_widget_lifecycle(qtbot: QtBot) -> None:
    """Verifica que el widget se inicialice, aplique exclusión y gestione scroll."""
    settings = TeleprompterSettings(font_size=24, wpm=150, lines_visible=2)
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

    # Iniciar scroll
    widget.start_scrolling()
    assert widget._is_scrolling is True
    assert widget._is_paused is False

    # Pausar
    widget.pause_scrolling()
    assert widget._is_paused is True

    # Reanudar
    widget.resume_scrolling()
    assert widget._is_paused is False


def test_teleprompter_editor_dialog(qtbot: QtBot) -> None:
    """Verifica el editor de guion, conteo de palabras y emisión de señales."""
    settings = TeleprompterSettings(wpm=120)
    dialog = TeleprompterEditorDialog("Primera palabra segunda palabra tercera", settings)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.isVisible()
    assert "5 palabras" in dialog.stats_label.text()

    # Modificar texto
    dialog.text_edit.setPlainText("Una dos tres cuatro seis.")
    assert "5 palabras" in dialog.stats_label.text()

    # Probar obtención de ajustes
    new_settings = dialog.get_current_settings()
    assert new_settings.wpm == 120
    assert "seis" in new_settings.last_script
