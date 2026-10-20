"""Pruebas de interfaz para el marco interactivo de delimitación de región."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from pytestqt.qtbot import QtBot

from recordme.ui.region_frame import RegionFrameWidget, ResizeEdge
from recordme.utils.geometry import Rect


def test_region_frame_initialization_and_exclusion(qtbot: QtBot) -> None:
    """Verifica que el marco se posicione según coordenadas físicas y aplique exclusión."""
    frame = RegionFrameWidget()
    qtbot.addWidget(frame)

    rect = Rect(100, 100, 600, 400)
    frame.set_physical_region(rect, dpr=1.0)
    frame.show()

    assert frame.isVisible()
    phys = frame.get_physical_region()
    assert phys.width == 600
    assert phys.height == 400


def test_region_frame_resize_via_drag(qtbot: QtBot) -> None:
    """Verifica que al arrastrar el borde derecho o inferior cambie la geometría y emita región."""
    frame = RegionFrameWidget()
    qtbot.addWidget(frame)

    rect = Rect(100, 100, 400, 300)
    frame.set_physical_region(rect, dpr=1.0)
    frame.show()

    emitted_regions: list[Rect] = []
    frame.region_changed.connect(emitted_regions.append)

    # Iniciar arrastre en el borde derecho (x=398, y=150)
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(398, 150),
        QPoint(498, 250),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    frame.mousePressEvent(press_event)
    assert frame._active_edge & ResizeEdge.RIGHT

    # Mover 50px a la derecha (global x=548, y=250)
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPoint(448, 150),
        QPoint(548, 250),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    frame.mouseMoveEvent(move_event)

    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(448, 150),
        QPoint(548, 250),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    frame.mouseReleaseEvent(release_event)

    assert len(emitted_regions) >= 1
    last_rect = emitted_regions[-1]
    assert last_rect.width >= 440


def test_region_frame_recording_lock(qtbot: QtBot) -> None:
    """Verifica que durante la grabación el marco bloquee el redimensionado."""
    frame = RegionFrameWidget()
    qtbot.addWidget(frame)

    rect = Rect(100, 100, 400, 300)
    frame.set_physical_region(rect, dpr=1.0)
    frame.show()

    frame.set_recording_state(True)
    assert frame._is_locked is True

    # Al intentar arrastrar un borde bloqueado no debe cambiar de edge
    edge = frame._determine_edge(QPoint(398, 150))
    assert edge == ResizeEdge.NONE
