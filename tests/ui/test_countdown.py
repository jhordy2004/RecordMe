"""Pruebas de interfaz para el overlay de cuenta regresiva (3, 2, 1)."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QKeyEvent
from pytestqt.qtbot import QtBot

from recordme.ui.countdown import CountdownOverlay


def test_countdown_overlay_centering_and_ticks(qtbot: QtBot) -> None:
    """Verifica que el overlay se centre en el rectángulo objetivo y descuente."""
    target = QRect(200, 100, 400, 300)
    overlay = CountdownOverlay(target_rect=target, seconds=2)
    qtbot.addWidget(overlay)
    overlay.show()

    assert overlay.isVisible()
    # Debe estar centrado en (400, 250)
    center = overlay.geometry().center()
    assert abs(center.x() - target.center().x()) <= 2
    assert abs(center.y() - target.center().y()) <= 2

    finished_called: list[bool] = []
    overlay.finished.connect(lambda: finished_called.append(True))

    # Ticks simulados
    overlay._on_tick()  # de 2 pasa a 1
    assert overlay._current_count == 1
    assert not finished_called

    overlay._on_tick()  # de 1 pasa a 0 -> emite finished y cierra
    assert len(finished_called) == 1
    assert not overlay.isVisible()


def test_countdown_overlay_cancel_with_escape(qtbot: QtBot) -> None:
    """Verifica que presionar Escape cancele la cuenta regresiva."""
    target = QRect(100, 100, 300, 200)
    overlay = CountdownOverlay(target_rect=target, seconds=3)
    qtbot.addWidget(overlay)
    overlay.start()

    canceled_called: list[bool] = []
    overlay.canceled.connect(lambda: canceled_called.append(True))

    esc_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    overlay.keyPressEvent(esc_event)

    assert len(canceled_called) == 1
    assert not overlay._timer.isActive()
    assert not overlay.isVisible()
