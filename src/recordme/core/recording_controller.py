"""Controlador de orquestación del ciclo de grabación completo (Video + Audio + Compositor + Muxer)."""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from recordme.audio.mic_recorder import MicRecorder
from recordme.camera.camera_source import CameraSource
from recordme.capture.base import CaptureBackend
from recordme.capture.factory import create_capture_backend
from recordme.capture.mss_fallback import MSSCaptureBackend
from recordme.capture.qt_fallback import QtScreenCaptureBackend
from recordme.compose.compositor import Compositor
from recordme.config.paths import get_temp_dir
from recordme.config.settings import AppSettings
from recordme.core.events import SessionState
from recordme.core.render_state import CameraLayout, RenderState
from recordme.core.session import SessionManager
from recordme.encode.muxer import Muxer
from recordme.encode.video_writer import VideoWriter
from recordme.utils.geometry import Rect, get_primary_screen_physical_rect

logger = logging.getLogger(__name__)


class RecordingController(QObject):
    """Orquesta el ciclo de vida de la grabación conectando captura, composición, audio y muxing."""

    recording_finished = Signal(Path)  # Emite la ruta del archivo final guardado
    recording_failed = Signal(str)     # Emite el mensaje de error

    def __init__(
        self,
        session_manager: SessionManager,
        settings: AppSettings,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.session_manager = session_manager
        self.settings = settings

        self.current_region: Rect = get_primary_screen_physical_rect()
        self._capture_backend: CaptureBackend | None = None
        self._video_writer: VideoWriter | None = None
        self._mic_recorder: MicRecorder | None = None
        self._camera_source: CameraSource | None = None
        self._camera_layout = CameraLayout(
            enabled=False,
            shape=self.settings.camera.shape,
            size_pct=self.settings.camera.size_pct,
            mirror=self.settings.camera.mirror,
            border_enabled=self.settings.camera.border.enabled,
            border_width=self.settings.camera.border.width,
            border_color=self.settings.camera.border.color,
            name_enabled=self.settings.camera.name.enabled,
            name_text=self.settings.camera.name.text,
            name_position=self.settings.camera.name.position,
        )
        self._compositor: Compositor | None = None
        self._muxer = Muxer()

        self._temp_video_file: Path | None = None
        self._temp_audio_file: Path | None = None
        self._output_file: Path | None = None

    @property
    def camera_source(self) -> CameraSource | None:
        """Devuelve la fuente de cámara activa si existe."""
        return self._camera_source

    @property
    def camera_layout(self) -> CameraLayout:
        """Devuelve el layout actual de la cámara."""
        return self._camera_layout

    def set_camera_enabled(self, enabled: bool) -> bool:
        """Activa o desactiva la cámara tanto en reposo como en plena grabación."""
        if enabled:
            if self._camera_source is None:
                self._camera_source = CameraSource(
                    fps=self.settings.output.fps,
                    mirror=self._camera_layout.mirror,
                )
                if not self._camera_source.start():
                    logger.warning("No se pudo iniciar CameraSource.")
                    self._camera_source = None
                    return False

            self._camera_layout = CameraLayout(
                enabled=True,
                shape=self._camera_layout.shape,
                center_norm_x=self._camera_layout.center_norm_x,
                center_norm_y=self._camera_layout.center_norm_y,
                size_pct=self._camera_layout.size_pct,
                mirror=self._camera_layout.mirror,
                border_enabled=self._camera_layout.border_enabled,
                border_width=self._camera_layout.border_width,
                border_color=self._camera_layout.border_color,
                name_enabled=self._camera_layout.name_enabled,
                name_text=self._camera_layout.name_text,
                name_position=self._camera_layout.name_position,
            )
        else:
            self._camera_layout = CameraLayout(
                enabled=False,
                shape=self._camera_layout.shape,
                center_norm_x=self._camera_layout.center_norm_x,
                center_norm_y=self._camera_layout.center_norm_y,
                size_pct=self._camera_layout.size_pct,
                mirror=self._camera_layout.mirror,
                border_enabled=self._camera_layout.border_enabled,
                border_width=self._camera_layout.border_width,
                border_color=self._camera_layout.border_color,
                name_enabled=self._camera_layout.name_enabled,
                name_text=self._camera_layout.name_text,
                name_position=self._camera_layout.name_position,
            )
            # Si no se está grabando, podemos detener el dispositivo para ahorrar energía
            if self.session_manager.state != SessionState.RECORDING and self._camera_source:
                self._camera_source.stop()
                self._camera_source = None

        if self._compositor is not None:
            self._compositor.camera_source = self._camera_source
            self._compositor.update_render_state(self._build_render_state())

        logger.info("Cámara %s", "activada" if enabled else "desactivada")
        return True

    def update_camera_layout(self, layout: CameraLayout) -> None:
        """Actualiza la posición y tamaño de la cámara en el compositor en tiempo real."""
        self._camera_layout = layout
        if self._compositor is not None:
            self._compositor.update_render_state(self._build_render_state())

    def _build_render_state(self) -> RenderState:
        """Construye un snapshot de RenderState inmutable para el Compositor."""
        return RenderState(
            capture_region=self.current_region,
            output_width=self.current_region.width,
            output_height=self.current_region.height,
            camera=self._camera_layout,
        )

    def set_region(self, region: Rect) -> None:
        """Establece la región de captura en coordenadas físicas."""
        self.current_region = region.to_even()
        logger.info("Región de captura configurada en controller: %s", self.current_region)

    def start_recording(self) -> bool:
        """Inicia el pipeline de grabación."""
        if self.session_manager.state not in (SessionState.IDLE, SessionState.CONFIGURING, SessionState.DONE):
            logger.warning("No se puede iniciar grabación desde estado: %s", self.session_manager.state.name)
            return False

        try:
            if self.session_manager.state == SessionState.IDLE:
                self.session_manager.transition_to(SessionState.CONFIGURING)
            timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            temp_dir = get_temp_dir()
            self._temp_video_file = temp_dir / f"temp_{timestamp_str}.mkv"
            self._temp_audio_file = temp_dir / f"temp_{timestamp_str}.wav"

            # Nombre final según plantilla
            filename = f"Grabacion_{timestamp_str}.mp4"
            dest_folder = Path(self.settings.output.folder)
            dest_folder.mkdir(parents=True, exist_ok=True)
            self._output_file = dest_folder / filename

            # 1. Iniciar backend de captura con fallback automático
            fps = self.settings.output.fps
            backends_to_try = [
                create_capture_backend(),
                MSSCaptureBackend(),
                QtScreenCaptureBackend(),
            ]
            self._capture_backend = None
            for backend in backends_to_try:
                try:
                    if backend.start(self.current_region, fps=fps):
                        self._capture_backend = backend
                        logger.info("Backend de captura seleccionado exitosamente: %s", type(backend).__name__)
                        break
                except Exception as ex:
                    logger.warning("Fallo al iniciar backend %s: %s", type(backend).__name__, ex)

            if self._capture_backend is None:
                raise RuntimeError("No se pudo iniciar ningún backend de captura de pantalla.")

            # Esperar un instante para que el backend entregue al menos un frame inicial
            time.sleep(0.08)

            # 2. Iniciar escritor de video
            self._video_writer = VideoWriter(
                output_file=self._temp_video_file,
                width=self.current_region.width,
                height=self.current_region.height,
                fps=fps,
            )
            if not self._video_writer.start():
                raise RuntimeError("No se pudo iniciar el proceso de FFmpeg para video.")

            # 3. Iniciar grabador de audio de micrófono si está habilitado
            if self.settings.audio.mic_enabled:
                self._mic_recorder = MicRecorder(output_file=self._temp_audio_file)
                self._mic_recorder.start()

            # 4. Iniciar compositor
            self._compositor = Compositor(
                capture_backend=self._capture_backend,
                video_writer=self._video_writer,
                initial_render_state=self._build_render_state(),
                camera_source=self._camera_source,
                fps=fps,
            )
            self._compositor.start()

            self.session_manager.transition_to(SessionState.RECORDING)
            logger.info("Grabación iniciada exitosamente. Archivo temporal video: %s", self._temp_video_file)
            return True

        except Exception as e:
            logger.exception("Error al iniciar grabación: %s", e)
            self._cleanup_resources()
            self.session_manager.transition_to(SessionState.ERROR, error_message=str(e))
            self.recording_failed.emit(str(e))
            return False

    def pause_recording(self) -> None:
        """Pausa la grabación."""
        if self.session_manager.state == SessionState.RECORDING:
            if self._compositor:
                self._compositor.set_paused(True)
            if self._mic_recorder:
                self._mic_recorder.set_paused(True)
            self.session_manager.transition_to(SessionState.PAUSED)
            logger.info("Grabación pausada.")

    def resume_recording(self) -> None:
        """Reanuda la grabación."""
        if self.session_manager.state == SessionState.PAUSED:
            if self._compositor:
                self._compositor.set_paused(False)
            if self._mic_recorder:
                self._mic_recorder.set_paused(False)
            self.session_manager.transition_to(SessionState.RECORDING)
            logger.info("Grabación reanudada.")

    def set_mic_muted(self, muted: bool) -> None:
        """Silencia o activa el micrófono."""
        if self._mic_recorder:
            self._mic_recorder.set_muted(muted)

    def stop_recording(self) -> None:
        """Detiene y finaliza la grabación, realizando el muxing A/V."""
        if self.session_manager.state not in (SessionState.RECORDING, SessionState.PAUSED):
            return

        self.session_manager.transition_to(SessionState.FINALIZING)
        logger.info("Deteniendo grabación y finalizando archivos...")

        # Detener componentes
        if self._compositor:
            self._compositor.stop()
        if self._capture_backend:
            self._capture_backend.stop()
        if self._mic_recorder:
            self._mic_recorder.stop()
        if self._video_writer:
            self._video_writer.close()

        # Calcular offset inicial entre video y audio
        offset_seconds = 0.0
        if (
            self._compositor
            and self._compositor.first_frame_time is not None
            and self._mic_recorder
            and self._mic_recorder.first_audio_time is not None
        ):
            # offset = primer_video - primer_audio
            offset_seconds = self._compositor.first_frame_time - self._mic_recorder.first_audio_time
            logger.info("Offset calculado A/V: %.4f segundos", offset_seconds)

        # Muxing a MP4 final
        assert self._temp_video_file is not None
        assert self._output_file is not None

        success = self._muxer.mux(
            video_path=self._temp_video_file,
            audio_path=self._temp_audio_file,
            output_mp4=self._output_file,
            offset_seconds=offset_seconds,
        )

        self._cleanup_resources()

        if success and self._output_file.exists():
            self.session_manager.transition_to(SessionState.DONE)
            logger.info("Grabación completada: %s", self._output_file)
            self.recording_finished.emit(self._output_file)
        else:
            msg = "Error durante el muxing final de FFmpeg."
            self.session_manager.transition_to(SessionState.ERROR, error_message=msg)
            self.recording_failed.emit(msg)

    def _cleanup_resources(self) -> None:
        """Libera punteros a componentes en ejecución."""
        self._compositor = None
        self._video_writer = None
        self._capture_backend = None
        self._mic_recorder = None
