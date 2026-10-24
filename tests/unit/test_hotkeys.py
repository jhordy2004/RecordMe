"""Pruebas unitarias para GlobalHotkeyService."""

import pytest
from pynput import keyboard
from pytestqt.qtbot import QtBot

from recordme.platform_services.hotkeys import GlobalHotkeyService


def test_hotkey_service_zoom_and_pan_signals(qtbot: QtBot) -> None:
    """Verifica que GlobalHotkeyService emita las señales correspondientes al presionar teclas con Alt."""
    service = GlobalHotkeyService()

    # 1. Simular presionar Alt
    service._on_press(keyboard.Key.alt_l)

    # 2. Alt + '+' -> zoom_in
    key_plus = keyboard.KeyCode.from_char("+")
    with qtbot.waitSignal(service.zoom_in, timeout=1000):
        service._on_press(key_plus)
    service._on_release(key_plus)

    # 3. Alt + '-' -> zoom_out
    key_minus = keyboard.KeyCode.from_char("-")
    with qtbot.waitSignal(service.zoom_out, timeout=1000):
        service._on_press(key_minus)
    service._on_release(key_minus)

    # 4. Alt + '0' -> zoom_reset
    key_zero = keyboard.KeyCode.from_char("0")
    with qtbot.waitSignal(service.zoom_reset, timeout=1000):
        service._on_press(key_zero)
    service._on_release(key_zero)

    # 5. Alt + Flechas -> pan
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

    # 6. Liberar Alt: ya no debe emitir
    service._on_release(keyboard.Key.alt_l)
    emitted = []
    service.zoom_in.connect(lambda: emitted.append("zoom_in"))
    service._on_press(key_plus)
    assert len(emitted) == 0

    service.stop()


def test_hotkey_service_direct_action_signals(qtbot: QtBot) -> None:
    """Verifica que GlobalHotkeyService emita señales con la combinación Alt+[Letra]."""
    service = GlobalHotkeyService()

    # Activar Alt
    service._on_press(keyboard.Key.alt_l)

    # 1. Alt+L -> trigger_area
    key_l = keyboard.KeyCode.from_char("l")
    with qtbot.waitSignal(service.trigger_area, timeout=1000):
        service._on_press(key_l)
    service._on_release(key_l)

    # 2. Alt+R -> trigger_record
    key_r = keyboard.KeyCode.from_char("r")
    with qtbot.waitSignal(service.trigger_record, timeout=1000):
        service._on_press(key_r)
    service._on_release(key_r)

    # 3. Alt+P -> trigger_pause
    key_p = keyboard.KeyCode.from_char("p")
    with qtbot.waitSignal(service.trigger_pause, timeout=1000):
        service._on_press(key_p)
    service._on_release(key_p)

    # 4. Alt+M -> trigger_mic
    key_m = keyboard.KeyCode.from_char("m")
    with qtbot.waitSignal(service.trigger_mic, timeout=1000):
        service._on_press(key_m)
    service._on_release(key_m)

    # 5. Alt+C -> trigger_camera
    key_c = keyboard.KeyCode.from_char("c")
    with qtbot.waitSignal(service.trigger_camera, timeout=1000):
        service._on_press(key_c)
    service._on_release(key_c)

    # 6. Alt+T -> trigger_teleprompter
    key_t = keyboard.KeyCode.from_char("t")
    with qtbot.waitSignal(service.trigger_teleprompter, timeout=1000):
        service._on_press(key_t)
    service._on_release(key_t)

    # 7. Alt+X -> trigger_censor
    key_x = keyboard.KeyCode.from_char("x")
    with qtbot.waitSignal(service.trigger_censor, timeout=1000):
        service._on_press(key_x)
    service._on_release(key_x)

    # 8. Alt+Q -> trigger_exit
    key_q = keyboard.KeyCode.from_char("q")
    with qtbot.waitSignal(service.trigger_exit, timeout=1000):
        service._on_press(key_q)
    service._on_release(key_q)

    # Liberar Alt
    service._on_release(keyboard.Key.alt_l)

    # 9. Teclas individuales sueltas (sin Alt) NO deben emitir ninguna acción
    emitted: list[str] = []
    service.trigger_area.connect(lambda: emitted.append("area"))
    service.trigger_record.connect(lambda: emitted.append("record"))
    service.trigger_camera.connect(lambda: emitted.append("camera"))
    service.trigger_teleprompter.connect(lambda: emitted.append("teleprompter"))
    service.trigger_exit.connect(lambda: emitted.append("exit"))

    for k in (key_l, key_r, key_c, key_t, key_q):
        service._on_press(k)
        service._on_release(k)
    assert len(emitted) == 0

    service.stop()


def test_hotkeys_suppression_when_external_app_focused(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que teclas sueltas al escribir palabras como 'encontrar' se ignoren totalmente,
    y que Ctrl+C / Ctrl+X / Ctrl+T respeten las funciones estándar del sistema y navegadores."""
    service = GlobalHotkeyService()

    emitted: list[str] = []
    service.trigger_camera.connect(lambda: emitted.append("camera"))
    service.trigger_teleprompter.connect(lambda: emitted.append("teleprompter"))
    service.trigger_record.connect(lambda: emitted.append("record"))
    service.trigger_censor.connect(lambda: emitted.append("censor"))

    # Escribir la palabra 'encontrar' letra por letra sin modificadores
    for ch in "encontrar":
        k = keyboard.KeyCode.from_char(ch)
        service._on_press(k)
        service._on_release(k)

    # Ninguna acción debe haberse activado
    assert len(emitted) == 0

    # Simular que hay un campo de texto o app externa activa (ej. Word, WhatsApp, buscador)
    monkeypatch.setattr(service, "_is_text_input_active_system_wide", lambda: True)

    # Presionar Ctrl+C, Ctrl+X, Ctrl+T NO debe disparar atajos de RecordMe
    service._on_press(keyboard.Key.ctrl_l)
    service._on_press(keyboard.KeyCode.from_char("c"))
    service._on_release(keyboard.KeyCode.from_char("c"))
    service._on_press(keyboard.KeyCode.from_char("x"))
    service._on_release(keyboard.KeyCode.from_char("x"))
    service._on_press(keyboard.KeyCode.from_char("t"))
    service._on_release(keyboard.KeyCode.from_char("t"))
    service._on_release(keyboard.Key.ctrl_l)
    assert len(emitted) == 0

    # Pero Alt+R sí debe funcionar como atajo global de grabación
    service._on_press(keyboard.Key.alt_l)
    with qtbot.waitSignal(service.trigger_record, timeout=1000):
        service._on_press(keyboard.KeyCode.from_char("r"))
    service._on_release(keyboard.KeyCode.from_char("r"))
    service._on_release(keyboard.Key.alt_l)

    service.stop()
