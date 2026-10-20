"""Pruebas unitarias para GlobalHotkeyService."""

from pynput import keyboard
from pytestqt.qtbot import QtBot

from recordme.platform_services.hotkeys import GlobalHotkeyService


def test_hotkey_service_zoom_and_pan_signals(qtbot: QtBot) -> None:
    """Verifica que GlobalHotkeyService emita las señales correspondientes al presionar teclas."""
    service = GlobalHotkeyService()

    # 1. Simular presionar Ctrl
    service._on_press(keyboard.Key.ctrl_l)

    # 2. Ctrl + '+' -> zoom_in
    key_plus = keyboard.KeyCode.from_char("+")
    with qtbot.waitSignal(service.zoom_in, timeout=1000):
        service._on_press(key_plus)
    service._on_release(key_plus)

    # 3. Ctrl + '-' -> zoom_out
    key_minus = keyboard.KeyCode.from_char("-")
    with qtbot.waitSignal(service.zoom_out, timeout=1000):
        service._on_press(key_minus)
    service._on_release(key_minus)

    # 4. Ctrl + '0' -> zoom_reset
    key_zero = keyboard.KeyCode.from_char("0")
    with qtbot.waitSignal(service.zoom_reset, timeout=1000):
        service._on_press(key_zero)
    service._on_release(key_zero)

    # 5. Ctrl + Flechas -> pan
    with qtbot.waitSignal(service.pan_up, timeout=1000):
        service._on_press(keyboard.Key.up)
    service._on_release(keyboard.Key.up)

    with qtbot.waitSignal(service.pan_down, timeout=1000):
        service._on_press(keyboard.Key.down)
    service._on_release(keyboard.Key.down)

    with qtbot.waitSignal(service.pan_left, timeout=1000):
        service._on_press(keyboard.Key.left)
    service._on_release(keyboard.Key.left)

    with qtbot.waitSignal(service.pan_right, timeout=1000):
        service._on_press(keyboard.Key.right)
    service._on_release(keyboard.Key.right)

    # 6. Liberar Ctrl: ya no debe emitir
    service._on_release(keyboard.Key.ctrl_l)
    emitted = []
    service.zoom_in.connect(lambda: emitted.append("zoom_in"))
    service._on_press(key_plus)
    assert len(emitted) == 0

    service.stop()
