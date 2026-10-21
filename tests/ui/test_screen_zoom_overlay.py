"""Pruebas unitarias para ScreenZoomOverlay."""

from pytestqt.qtbot import QtBot

from recordme.ui.screen_zoom_overlay import ScreenZoomOverlay


def test_screen_zoom_overlay_lifecycle(qtbot: QtBot) -> None:
    """Verifica que el overlay se muestre cuando el zoom supera 1.0x y se oculte en 1.0x."""
    overlay = ScreenZoomOverlay()
    qtbot.addWidget(overlay)

    # Inicialmente oculto
    assert not overlay.isVisible()

    # Activar zoom al 120%
    overlay.set_zoom(1.20, 0.5, 0.5)
    assert overlay._zoom_level == 1.20
    assert overlay.isVisible()
    assert overlay._refresh_timer.isActive()

    # Volver a 100%
    overlay.set_zoom(1.0, 0.5, 0.5)
    assert overlay._zoom_level == 1.0
    assert not overlay.isVisible()
    assert not overlay._refresh_timer.isActive()
