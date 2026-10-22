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


def test_hotkey_service_direct_action_signals(qtbot: QtBot) -> None:
    """Verifica que GlobalHotkeyService emita señales directas para L, R, P, M, C, T, X, Q."""
    service = GlobalHotkeyService()

    # 1. L -> trigger_area
    key_l = keyboard.KeyCode.from_char("l")
    with qtbot.waitSignal(service.trigger_area, timeout=1000):
        service._on_press(key_l)
    service._on_release(key_l)

    # 2. R -> trigger_record
    key_r = keyboard.KeyCode.from_char("r")
    with qtbot.waitSignal(service.trigger_record, timeout=1000):
        service._on_press(key_r)
    service._on_release(key_r)

    # 3. P -> trigger_pause
    key_p = keyboard.KeyCode.from_char("p")
    with qtbot.waitSignal(service.trigger_pause, timeout=1000):
        service._on_press(key_p)
    service._on_release(key_p)

    # 4. M -> trigger_mic
    key_m = keyboard.KeyCode.from_char("m")
    with qtbot.waitSignal(service.trigger_mic, timeout=1000):
        service._on_press(key_m)
    service._on_release(key_m)

    # 5. C -> trigger_camera
    key_c = keyboard.KeyCode.from_char("c")
    with qtbot.waitSignal(service.trigger_camera, timeout=1000):
        service._on_press(key_c)
    service._on_release(key_c)

    # 6. T -> trigger_teleprompter
    key_t = keyboard.KeyCode.from_char("t")
    with qtbot.waitSignal(service.trigger_teleprompter, timeout=1000):
        service._on_press(key_t)
    service._on_release(key_t)

    # 7. X -> trigger_censor
    key_x = keyboard.KeyCode.from_char("x")
    with qtbot.waitSignal(service.trigger_censor, timeout=1000):
        service._on_press(key_x)
    service._on_release(key_x)

    # 8. Q -> trigger_exit
    key_q = keyboard.KeyCode.from_char("q")
    with qtbot.waitSignal(service.trigger_exit, timeout=1000):
        service._on_press(key_q)
    service._on_release(key_q)

    # 9. Con Ctrl presionado no debe emitir hotkeys de una sola letra
    service._on_press(keyboard.Key.ctrl_l)
    emitted: list[str] = []
    service.trigger_area.connect(lambda: emitted.append("area"))
    service.trigger_record.connect(lambda: emitted.append("record"))
    service._on_press(key_l)
    service._on_press(key_r)
    service._on_release(keyboard.Key.ctrl_l)
    assert len(emitted) == 0

    # 10. Con text_input_active no debe emitir
    service.set_text_input_active(True)
    service._on_press(key_l)
    assert len(emitted) == 0
    service.set_text_input_active(False)

    service.stop()
