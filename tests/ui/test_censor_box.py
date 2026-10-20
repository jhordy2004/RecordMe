"""Pruebas unitarias para el widget interactivo CensorBoxWidget."""

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent
from pytestqt.qtbot import QtBot

from recordme.ui.censor_box import BoxEdge, CensorBoxWidget


def test_censor_box_initialization(qtbot: QtBot) -> None:
    """Verifica la inicialización adecuada de CensorBoxWidget."""
    initial_rect = QRect(100, 100, 200, 150)
    box = CensorBoxWidget(box_id="test-box-1", initial_rect=initial_rect, mode="blur", dpr=1.0)
    qtbot.addWidget(box)
    box.show()

    assert box.box_id == "test-box-1"
    assert box.mode == "blur"
    assert box.geometry() == initial_rect
    phys = box.get_physical_region()
    assert phys.width == 200
    assert phys.height == 150
    assert phys.x == 100
    assert phys.y == 100


def test_censor_box_mode_cycle(qtbot: QtBot) -> None:
    """Verifica el cambio secuencial de modo al hacer clic en el botón de modo."""
    initial_rect = QRect(50, 50, 200, 100)
    box = CensorBoxWidget(box_id="mode-box", initial_rect=initial_rect, mode="blur", dpr=1.0)
    qtbot.addWidget(box)
    box.show()

    # Simular clic dentro de _btn_mode_rect
    btn_rect = box._btn_mode_rect
    click_pos = QPoint(btn_rect.center().x(), btn_rect.center().y())

    with qtbot.waitSignal(box.geometry_changed) as blocker:
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            click_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        box.mousePressEvent(event)

    assert box.mode == "pixelate"
    assert blocker.args[2] == "pixelate"

    # Siguiente clic -> solid
    with qtbot.waitSignal(box.geometry_changed) as blocker:
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            click_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        box.mousePressEvent(event)

    assert box.mode == "solid"
    assert blocker.args[2] == "solid"


def test_censor_box_close_button(qtbot: QtBot) -> None:
    """Verifica que hacer clic en la X emita box_closed y cierre el widget."""
    initial_rect = QRect(50, 50, 200, 100)
    box = CensorBoxWidget(box_id="close-box", initial_rect=initial_rect, mode="blur", dpr=1.0)
    qtbot.addWidget(box)
    box.show()

    btn_rect = box._btn_close_rect
    click_pos = QPoint(btn_rect.center().x(), btn_rect.center().y())

    with qtbot.waitSignal(box.box_closed) as blocker:
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            click_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        box.mousePressEvent(event)

    assert blocker.args[0] == "close-box"
    assert not box.isVisible()


def test_censor_box_edge_detection() -> None:
    """Verifica la detección de bordes para redimensionamiento."""
    initial_rect = QRect(100, 100, 200, 100)
    box = CensorBoxWidget(box_id="edge-box", initial_rect=initial_rect, mode="blur", dpr=1.0)

    # Esquina superior izquierda (x <= BORDER_GRAB, y <= BORDER_GRAB)
    assert box._determine_edge(QPoint(2, 2)) == BoxEdge.TOP_LEFT
    # Esquina inferior derecha
    assert box._determine_edge(QPoint(198, 98)) == BoxEdge.BOTTOM_RIGHT
    # Borde izquierdo
    assert box._determine_edge(QPoint(2, 50)) == BoxEdge.LEFT
    # Interior -> MOVE
    assert box._determine_edge(QPoint(100, 50)) == BoxEdge.MOVE
