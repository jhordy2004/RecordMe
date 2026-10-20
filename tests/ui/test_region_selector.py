"""Pruebas de interfaz para el overlay de selección de región."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from pytestqt.qtbot import QtBot

from recordme.ui.region_selector import RegionSelectorOverlay
from recordme.utils.geometry import Rect


def test_region_selector_auto_confirm_on_drag(qtbot: QtBot) -> None:
    """Verifica que al arrastrar y soltar el ratón se confirme automáticamente la región."""
    overlay = RegionSelectorOverlay()
    qtbot.addWidget(overlay)
    overlay.show()

    emitted_regions: list[Rect] = []
    overlay.region_selected.connect(emitted_regions.append)

    # Simular inicio de arrastre en (50, 50)
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(50, 50),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(press_event)

    # Simular movimiento a (250, 200)
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPoint(250, 200),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseMoveEvent(move_event)

    # Simular soltar el botón izquierdo -> debe confirmar y emitir automáticamente
    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(250, 200),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseReleaseEvent(release_event)

    assert len(emitted_regions) == 1
    rect = emitted_regions[0]
    assert rect.width >= 100
    assert rect.height >= 100
    assert not overlay.isVisible()
