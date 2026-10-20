"""Pruebas de interfaz para la ventana de bienvenida."""

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from recordme.app import WelcomeWindow
from recordme.config.settings import AppSettings
from recordme.core.session import SessionManager


def test_welcome_window_creation(qtbot: QtBot) -> None:
    """Verifica la creación y visualización de la ventana de bienvenida."""
    session_manager = SessionManager()
    settings = AppSettings()
    window = WelcomeWindow(session_manager, settings)
    qtbot.addWidget(window)
    window.show()

    assert window.isVisible()
    assert "RecordMe" in window.windowTitle()

    # Probar clic en Comprobar Servicios
    qtbot.mouseClick(window.status_btn, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
    assert "Exclusión captura:" in window.status_btn.text()
