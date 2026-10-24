"""Prueba de integración end-to-end del RecordingController."""

from pathlib import Path

from pytestqt.qtbot import QtBot

from recordme.config.settings import AppSettings
from recordme.core.recording_controller import RecordingController
from recordme.core.session import SessionManager
from recordme.utils.geometry import Rect


def test_recording_controller_lifecycle(qtbot: QtBot, tmp_path: Path) -> None:
    """Verifica el ciclo completo start -> pause -> resume -> stop con generación de MP4."""
    session_manager = SessionManager()
    settings = AppSettings()
    settings.output.folder = str(tmp_path)
    settings.output.fps = 20

    controller = RecordingController(session_manager, settings)
    controller.set_region(Rect(0, 0, 320, 240))

    finished_file: list[Path] = []
    controller.recording_finished.connect(lambda p: finished_file.append(p))

    # Iniciar grabación
    started = controller.start_recording()
    assert started is True
    assert session_manager.state.name == "RECORDING"

    # Grabar durante 1 segundo
    qtbot.wait(1000)

    # Pausar
    controller.pause_recording()
    assert session_manager.state.name == "PAUSED"
    qtbot.wait(500)

    # Reanudar
    controller.resume_recording()
    assert session_manager.state.name == "RECORDING"
    qtbot.wait(500)

    # Detener y esperar finalización
    with qtbot.waitSignal(controller.recording_finished, timeout=10000):
        controller.stop_recording()

    assert session_manager.state.name == "DONE"
    assert len(finished_file) == 1
    output_mp4 = finished_file[0]
    assert output_mp4.exists()
    assert output_mp4.stat().st_size > 3000


def test_recording_controller_consecutive_runs(qtbot: QtBot, tmp_path: Path) -> None:
    """Verifica que tras detener una grabación se pueda iniciar de inmediato una segunda grabación."""
    session_manager = SessionManager()
    settings = AppSettings()
    settings.output.folder = str(tmp_path)
    settings.output.fps = 20

    controller = RecordingController(session_manager, settings)
    controller.set_region(Rect(0, 0, 320, 240))

    # Primera grabación
    assert controller.start_recording() is True
    qtbot.wait(400)
    with qtbot.waitSignal(controller.recording_finished, timeout=10000):
        controller.stop_recording()
    assert session_manager.state.name == "DONE"

    # Segunda grabación inmediata sin errores de transición
    assert controller.start_recording() is True
    assert session_manager.state.name == "RECORDING"
    qtbot.wait(400)
    with qtbot.waitSignal(controller.recording_finished, timeout=10000):
        controller.stop_recording()
    assert session_manager.state.name == "DONE"


def test_recording_controller_start_from_countdown(qtbot: QtBot, tmp_path: Path) -> None:
    """Verifica que el controlador inicie la grabación correctamente desde el estado COUNTDOWN."""
    from recordme.core.events import SessionState

    session_manager = SessionManager()
    session_manager.transition_to(SessionState.COUNTDOWN)

    settings = AppSettings()
    settings.output.folder = str(tmp_path)
    settings.output.fps = 20

    controller = RecordingController(session_manager, settings)
    controller.set_region(Rect(0, 0, 320, 240))

    assert controller.start_recording() is True
    assert session_manager.state == SessionState.RECORDING
    qtbot.wait(400)
    with qtbot.waitSignal(controller.recording_finished, timeout=10000):
        controller.stop_recording()
    assert session_manager.state == SessionState.DONE

