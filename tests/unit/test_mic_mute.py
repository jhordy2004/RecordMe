"""Pruebas unitarias para el comportamiento de mute/silencio del micrófono."""

from pathlib import Path

import numpy as np

from recordme.audio.mic_recorder import MicRecorder
from recordme.config.settings import AppSettings
from recordme.core.recording_controller import RecordingController
from recordme.core.session import SessionManager


def test_mic_recorder_mute_writes_silence(tmp_path: Path) -> None:
    """Verifica que cuando el grabador está silenciado, la cola reciba silencio de ceros."""
    wav_path = tmp_path / "test_silence.wav"
    recorder = MicRecorder(output_file=wav_path)

    # Simular callback con señal de audio no nula
    audio_data = np.ones((512, 1), dtype=np.float32) * 0.8
    recorder._is_recording = True
    recorder._is_muted = True

    recorder._audio_callback(
        indata=audio_data,
        frames=512,
        time_info=None,
        status=None,
    )

    block = recorder._queue.get_nowait()
    assert block is not None
    assert np.all(block == 0.0)


def test_recording_controller_mic_state_sync() -> None:
    """Verifica que el controlador almacene el estado y aplique mute correctamente."""
    session_manager = SessionManager()
    settings = AppSettings()
    controller = RecordingController(session_manager, settings)

    # Inicialmente mic_enabled es True
    assert controller._mic_enabled is True

    # Desactivar micrófono
    controller.set_mic_enabled(False)
    assert controller._mic_enabled is False
    assert controller.settings.audio.mic_enabled is False

    # Activar micrófono
    controller.set_mic_enabled(True)
    assert controller._mic_enabled is True
    assert controller.settings.audio.mic_enabled is True
