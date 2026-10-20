"""Pruebas de interfaz para el editor de regiones de censura."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from pytestqt.qtbot import QtBot

from recordme.core.render_state import CensorRegion
from recordme.ui.censor_overlay import CensorOverlay
from recordme.utils.geometry import Rect


def test_censor_overlay_add_region_via_drag(qtbot: QtBot) -> None:
    """Verifica que al arrastrar sobre el overlay se agregue una región de censura."""
    overlay = CensorOverlay()
    qtbot.addWidget(overlay)
    overlay.show()

    emitted_regions: list[list[CensorRegion]] = []
    overlay.regions_changed.connect(emitted_regions.append)

    # Iniciar trazado en (50, 50)
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(50, 50),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(press_event)

    # Mover a (150, 120)
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPoint(150, 120),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseMoveEvent(move_event)

    # Soltar
    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(150, 120),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseReleaseEvent(release_event)

    assert len(overlay._regions) == 1
    reg = overlay._regions[0]
    assert reg.mode == "blur"
    assert reg.rect.width >= 50
    assert reg.rect.height >= 50


def test_censor_overlay_clear_all(qtbot: QtBot) -> None:
    """Verifica que el botón de borrar todas limpie la lista de censura."""
    initial = [CensorRegion(id="r1", rect=Rect(10, 10, 50, 50), mode="blur")]
    overlay = CensorOverlay(existing_regions=initial)
    qtbot.addWidget(overlay)
    overlay.show()

    assert len(overlay._regions) == 1
    overlay._clear_all()
    assert len(overlay._regions) == 0
