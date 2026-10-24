"""Pruebas unitarias para las correcciones de atajos en navegador/diapositivas, loopback de audio, calidad de sonido y estabilidad de cámara."""

from pathlib import Path

import numpy as np
import pytest
from pynput import keyboard
from pytestqt.qtbot import QtBot

from recordme.audio.mic_recorder import MicRecorder
from recordme.core.render_state import CameraLayout
from recordme.platform_services.hotkeys import GlobalHotkeyService
from recordme.ui.camera_preview import CameraPreviewWidget
from recordme.utils.geometry import Rect


def test_hotkeys_work_in_browser_or_slides_when_not_in_input(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que combinaciones Alt+C, Alt+T, Alt+R funcionen globalmente fuera de campos de texto."""
    service = GlobalHotkeyService()

    # Simular que NO hay ningún input de texto activo (ej. diapositivas o YouTube)
    monkeypatch.setattr(service, "_is_text_input_active_system_wide", lambda: False)

    emitted: list[str] = []
    service.trigger_camera.connect(lambda: emitted.append("camera"))
    service.trigger_teleprompter.connect(lambda: emitted.append("teleprompter"))
    service.trigger_record.connect(lambda: emitted.append("record"))

    service._on_press(keyboard.Key.alt_l)

    # Presionar Alt+C -> debe disparar cámara
    with qtbot.waitSignal(service.trigger_camera, timeout=1000):
        service._on_press(keyboard.KeyCode.from_char("c"))
    service._on_release(keyboard.KeyCode.from_char("c"))

    # Presionar Alt+T -> debe disparar teleprompter
    with qtbot.waitSignal(service.trigger_teleprompter, timeout=1000):
        service._on_press(keyboard.KeyCode.from_char("t"))
    service._on_release(keyboard.KeyCode.from_char("t"))

    # Presionar Alt+R -> debe disparar grabación
    with qtbot.waitSignal(service.trigger_record, timeout=1000):
        service._on_press(keyboard.KeyCode.from_char("r"))
    service._on_release(keyboard.KeyCode.from_char("r"))

    service._on_release(keyboard.Key.alt_l)

    assert "camera" in emitted
    assert "teleprompter" in emitted
    assert "record" in emitted
    service.stop()


def test_hotkeys_suppressed_only_when_in_input_field(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que al escribir en un input (ej. palabra 'encontrar') no se dispare ninguna acción directa."""
    service = GlobalHotkeyService()

    # Simular que el usuario tiene el cursor en un input de texto
    monkeypatch.setattr(service, "_is_text_input_active_system_wide", lambda: True)

    emitted: list[str] = []
    service.trigger_camera.connect(lambda: emitted.append("camera"))
    service.trigger_teleprompter.connect(lambda: emitted.append("teleprompter"))
    service.trigger_record.connect(lambda: emitted.append("record"))

    for ch in "encontrar":
        k = keyboard.KeyCode.from_char(ch)
        service._on_press(k)
        service._on_release(k)

    # Cero acciones disparadas por teclas sueltas
    assert len(emitted) == 0

    # Atajos con Alt siguen funcionando
    service._on_press(keyboard.Key.alt_l)
    with qtbot.waitSignal(service.trigger_camera, timeout=1000):
        service._on_press(keyboard.KeyCode.from_char("c"))
    service._on_release(keyboard.KeyCode.from_char("c"))
    service._on_release(keyboard.Key.alt_l)

    assert "camera" in emitted
    service.stop()


def test_audio_processing_pipeline(tmp_path: Path) -> None:
    """Verifica que el pipeline de filtrado pasaaltos 80Hz + supresión suave + normalización funcione sin distorsión."""
    import soundfile as sf

    sr = 48000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    # Tono puro de 300 Hz (voz) + ruido blanco suave + 60 Hz zumbido
    voice = 0.20 * np.sin(2 * np.pi * 300 * t)
    noise = 0.02 * np.random.normal(0, 1, len(t))
    hum = 0.05 * np.sin(2 * np.pi * 60 * t)
    audio = (voice + noise + hum).astype(np.float32)

    wav_file = tmp_path / "test_audio.wav"
    sf.write(str(wav_file), audio, sr, subtype="PCM_16")

    recorder = MicRecorder(output_file=wav_file, samplerate=sr, noise_reduction=True)
    recorder._apply_noise_reduction(wav_file)

    assert wav_file.exists()
    processed, proc_sr = sf.read(str(wav_file), dtype="float32")
    assert proc_sr == sr
    assert len(processed) == len(audio)

    # Verificar que el pico se normalizó adecuadamente sin clipping
    peak = float(np.max(np.abs(processed)))
    assert 0.70 <= peak <= 1.0


def test_audio_mix_headroom_limiting(tmp_path: Path) -> None:
    """Verifica que la mezcla de micrófono y audio del sistema aplique headroom y evite clipping."""
    import soundfile as sf

    sr = 48000
    # Dos señales de amplitud 0.9 cada una (si se sumaran directamente darían 1.8 = clipping severo)
    sig_mic = np.full((sr, 2), 0.90, dtype=np.float32)
    sig_sys = np.full((sr, 2), 0.90, dtype=np.float32)

    mic_file = tmp_path / "mic.wav"
    sys_file = tmp_path / "sys.wav"
    out_file = tmp_path / "mixed.wav"

    sf.write(str(mic_file), sig_mic, sr, subtype="PCM_16")
    sf.write(str(sys_file), sig_sys, sr, subtype="PCM_16")

    recorder = MicRecorder(output_file=out_file, samplerate=sr, mode="mic_and_system")
    recorder._mix_mic_and_system(mic_file, sys_file, out_file)

    assert out_file.exists()
    mixed, _ = sf.read(str(out_file), dtype="float32")
    max_peak = float(np.max(np.abs(mixed)))
    # El limitador suave debe mantener el pico en o por debajo de 0.95
    assert max_peak <= 0.96


def test_camera_preview_thread_safety(qtbot: QtBot) -> None:
    """Verifica que CameraPreviewWidget reciba frames y actualice su pixmap de forma segura."""
    layout = CameraLayout(enabled=True, shape="rect", size_pct=25)
    widget = CameraPreviewWidget(initial_layout=layout, capture_region=Rect(0, 0, 1920, 1080))
    qtbot.addWidget(widget)
    widget.show()

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    widget.update_frame(frame)
    assert widget._current_pixmap is not None
    assert not widget._current_pixmap.isNull()


def test_dxcam_check_availability_does_not_call_release(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que _check_dxcam_available no llame a cam.release() para evitar destruir el duplicador COM."""
    from recordme.capture import factory

    # Reset cache
    monkeypatch.setattr(factory, "_dxcam_available", None)

    class MockCam:
        def __init__(self):
            self.release_called = False

        def release(self):
            self.release_called = True
            raise RuntimeError("cam.release() must NOT be called in _check_dxcam_available!")

    mock_instance = MockCam()
    monkeypatch.setattr("dxcam.create", lambda *args, **kwargs: mock_instance)

    assert factory._check_dxcam_available() is True
    assert mock_instance.release_called is False


def test_initiate_recording_handles_prewarm_failure(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que si el pre-calentamiento falla, _initiate_recording regrese a IDLE sin lanzar la cuenta atrás."""
    from recordme.app import RecordMeApp
    from recordme.config.settings import AppSettings
    from recordme.core.session import SessionManager, SessionState

    session = SessionManager()
    settings = AppSettings()
    app = RecordMeApp(session, settings)
    qtbot.addWidget(app.toolbar)

    # Simular fallo en start_recording durante standby_countdown
    monkeypatch.setattr(app.controller, "start_recording", lambda standby_countdown=False: False)

    app._initiate_recording()

    # Debe permanecer o regresar a IDLE y NO debe haber un countdown_overlay activo
    assert session.state == SessionState.IDLE
    assert app.countdown_overlay is None
