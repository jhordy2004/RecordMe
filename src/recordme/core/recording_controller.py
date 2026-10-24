"""Controlador de orquestación del ciclo de grabación completo (Video + Audio + Compositor + Muxer)."""

import logging
import threading
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
from recordme.config.settings import AppSettings, AudioSettings, CameraSettings
from recordme.core.events import SessionState
from recordme.core.render_state import CameraLayout, CensorRegion, RenderState
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
            virtual_bg_image=self.settings.camera.background.image if self.settings.camera.background.mode == "image" else None,
        )
        self._compositor: Compositor | None = None
        self._muxer = Muxer()
        self._mic_enabled: bool = self.settings.audio.mic_enabled

        self._target_zoom: float = 1.0
        self._target_zoom_cx: float = 0.5
        self._target_zoom_cy: float = 0.5
        self._censor_regions: list[CensorRegion] = []

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
                virtual_bg_image=self._camera_layout.virtual_bg_image,
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
                virtual_bg_image=self._camera_layout.virtual_bg_image,
            )
            # Detener el dispositivo de cámara para apagar el sensor y la luz LED
            if self._camera_source is not None:
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

    def apply_camera_settings(self, settings: CameraSettings) -> None:
        """Aplica la configuración personalizada de la cámara (forma, nombre, fondo)."""
        self.settings.camera = settings
        self.settings.save()
        self._camera_layout = CameraLayout(
            enabled=self._camera_layout.enabled,
            shape=settings.shape,
            center_norm_x=self._camera_layout.center_norm_x,
            center_norm_y=self._camera_layout.center_norm_y,
            size_pct=self._camera_layout.size_pct,
            mirror=settings.mirror,
            border_enabled=settings.border.enabled,
            border_width=settings.border.width,
            border_color=settings.border.color,
            name_enabled=settings.name.enabled,
            name_text=settings.name.text,
            name_position=settings.name.position,
            virtual_bg_image=settings.background.image if settings.background.mode == "image" else None,
        )
        if self._compositor is not None:
            self._compositor.update_render_state(self._build_render_state())
        logger.info("Ajustes de cámara aplicados: forma=%s, nombre=%s", settings.shape, settings.name.text)

    def set_zoom(self, zoom: float, center_x: float = 0.5, center_y: float = 0.5) -> None:
        """Establece el nivel de zoom y su centro normalizado (0.0 a 1.0)."""
        self._target_zoom = max(1.0, min(zoom, 5.0))
        self._target_zoom_cx = max(0.0, min(center_x, 1.0))
        self._target_zoom_cy = max(0.0, min(center_y, 1.0))
        if self._compositor is not None:
            self._compositor.update_render_state(self._build_render_state())
        logger.debug("Zoom actualizado: %.2fx en (%.2f, %.2f)", self._target_zoom, self._target_zoom_cx, self._target_zoom_cy)

    def set_censor_regions(self, regions: list[CensorRegion]) -> None:
        """Actualiza las regiones de censura activas."""
        self._censor_regions = list(regions)
        if self._compositor is not None:
            self._compositor.update_render_state(self._build_render_state())
        logger.info("Regiones de censura actualizadas: %d regiones activas.", len(self._censor_regions))

    def add_censor_region(self, region: CensorRegion) -> None:
        """Agrega una nueva región de censura."""
        self._censor_regions.append(region)
        if self._compositor is not None:
            self._compositor.update_render_state(self._build_render_state())

    def clear_censor_regions(self) -> None:
        """Elimina todas las regiones de censura."""
        self._censor_regions.clear()
        if self._compositor is not None:
            self._compositor.update_render_state(self._build_render_state())

    def _build_render_state(self) -> RenderState:
        """Construye un snapshot de RenderState inmutable para el Compositor."""
        return RenderState(
            capture_region=self.current_region,
            output_width=self.current_region.width,
            output_height=self.current_region.height,
            camera=self._camera_layout,
            target_zoom=self._target_zoom,
            target_center_x=self._target_zoom_cx,
            target_center_y=self._target_zoom_cy,
            censor_regions=tuple(self._censor_regions),
        )

    def set_region(self, region: Rect) -> None:
        """Establece la región de captura en coordenadas físicas."""
        self.current_region = region.to_even()
        logger.info("Región de captura configurada en controller: %s", self.current_region)

    def apply_audio_settings(self, settings: AudioSettings) -> None:
        """Actualiza los ajustes de audio activos."""
        self.settings.audio = settings
        self.set_mic_enabled(settings.mic_enabled)
        logger.info("Ajustes de audio actualizados en controller: modo=%s, ruido=%s", settings.mode, settings.noise_reduction)

    def start_recording(self, standby_countdown: bool = False) -> bool:
        """Inicia el pipeline de grabación.

        Si standby_countdown es True, inicializa y pre-calienta todos los backends y subprocesos
        durante la cuenta atrás para que al llegar a 0 la grabación empiece instantáneamente con 0ms de demora.
        """
        if self.session_manager.state not in (
            SessionState.IDLE,
            SessionState.CONFIGURING,
            SessionState.COUNTDOWN,
            SessionState.DONE,
        ):
            logger.warning("No se puede iniciar grabación desde estado: %s", self.session_manager.state.name)
            return False

        try:
            if self.session_manager.state in (SessionState.IDLE, SessionState.DONE):
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

            # 1. Iniciar backend de captura con fallback automático sin instanciaciones redundantes
            fps = self.settings.output.fps
            primary_backend = create_capture_backend()
            backends_to_try = [primary_backend]
            if not isinstance(primary_backend, MSSCaptureBackend):
                backends_to_try.append(MSSCaptureBackend())
            if not isinstance(primary_backend, QtScreenCaptureBackend):
                backends_to_try.append(QtScreenCaptureBackend())

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

            # 3. Iniciar grabador de audio de micrófono y sistema
            dev_idx = None
            if self.settings.audio.mic_device != "default":
                try:
                    dev_idx = int(self.settings.audio.mic_device)
                except ValueError:
                    pass

            self._mic_recorder = MicRecorder(
                output_file=self._temp_audio_file,
                device_index=dev_idx,
                mode=self.settings.audio.mode,
                noise_reduction=self.settings.audio.noise_reduction,
                gain_db=self.settings.audio.mic_gain_db,
            )
            self._mic_recorder.set_muted(not self._mic_enabled)
            if standby_countdown:
                self._mic_recorder.set_recording_active(False)
            self._mic_recorder.start()

            # 4. Iniciar compositor
            self._compositor = Compositor(
                capture_backend=self._capture_backend,
                video_writer=self._video_writer,
                initial_render_state=self._build_render_state(),
                camera_source=self._camera_source,
                fps=fps,
            )
            if standby_countdown:
                self._compositor.set_recording_active(False)
            self._compositor.start()

            if not standby_countdown:
                self.session_manager.transition_to(SessionState.RECORDING)
                logger.info("Grabación iniciada exitosamente. Archivo temporal video: %s", self._temp_video_file)
            else:
                logger.info("Pipeline de grabación pre-calentado en standby durante cuenta atrás.")
            return True

        except Exception as e:
            logger.exception("Error al iniciar grabación: %s", e)
            self._cleanup_resources()
            self.session_manager.transition_to(SessionState.ERROR, error_message=str(e))
            self.recording_failed.emit(str(e))
            return False

    def activate_recording(self) -> bool:
        """Activa instantáneamente la persistencia de video y audio tras finalizar la cuenta atrás (0 ms de latencia)."""
        if self._compositor:
            self._compositor.set_recording_active(True)
        if self._mic_recorder:
            self._mic_recorder.set_recording_active(True)
        self.session_manager.transition_to(SessionState.RECORDING)
        logger.info("Grabación activada instantáneamente tras concluir la cuenta atrás.")
        return True

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

    def set_mic_enabled(self, enabled: bool) -> None:
        """Habilita o silencia el micrófono."""
        self._mic_enabled = enabled
        self.settings.audio.mic_enabled = enabled
        if self._mic_recorder:
            self._mic_recorder.set_muted(not enabled)
        logger.info("Micrófono en controller: %s", "habilitado" if enabled else "silenciado")

    def set_mic_muted(self, muted: bool) -> None:
        """Silencia o activa el micrófono (compatibilidad)."""
        self.set_mic_enabled(not muted)

    def cancel_recording(self) -> None:
        """Detiene y cancela la grabación sin muxear ni guardar nada, limpiando temporales."""
        if self.session_manager.state not in (SessionState.RECORDING, SessionState.PAUSED):
            return

        logger.info("Cancelando grabación en curso sin guardar...")
        if self._compositor:
            self._compositor.stop()
        if self._capture_backend:
            self._capture_backend.stop()
        if self._mic_recorder:
            self._mic_recorder.stop()
        if self._video_writer:
            self._video_writer.close()

        # Eliminar archivos temporales
        if self._temp_video_file and self._temp_video_file.exists():
            try:
                self._temp_video_file.unlink()
            except OSError:
                pass
        if self._temp_audio_file and self._temp_audio_file.exists():
            try:
                self._temp_audio_file.unlink()
            except OSError:
                pass

        self._cleanup_resources()
        self.session_manager.transition_to(SessionState.IDLE)
        logger.info("Grabación cancelada y descartada exitosamente.")

    def stop_recording(self, target_output_file: Path | None = None) -> None:
        """Detiene y finaliza la grabación de forma asíncrona y segura sin congelar el hilo principal."""
        if self.session_manager.state not in (SessionState.RECORDING, SessionState.PAUSED):
            return

        self.session_manager.transition_to(SessionState.FINALIZING)
        logger.info("Deteniendo grabación y finalizando archivos...")

        output_file = target_output_file if target_output_file is not None else self._output_file
        temp_video = self._temp_video_file
        temp_audio = self._temp_audio_file
        compositor = self._compositor
        capture_backend = self._capture_backend
        mic_recorder = self._mic_recorder
        video_writer = self._video_writer
        muxer = self._muxer

        # Desvincular referencias inmediatamente
        self._compositor = None
        self._capture_backend = None
        self._mic_recorder = None
        self._video_writer = None

        def _finalize_worker() -> None:
            try:
                # 1. Detener componentes con manejo de errores individual
                if compositor:
                    try:
                        compositor.stop()
                    except Exception as ex:
                        logger.warning("Error deteniendo compositor: %s", ex)

                if capture_backend:
                    try:
                        capture_backend.stop()
                    except Exception as ex:
                        logger.warning("Error deteniendo backend de captura: %s", ex)

                if mic_recorder:
                    try:
                        mic_recorder.stop()
                    except Exception as ex:
                        logger.warning("Error deteniendo mic recorder: %s", ex)

                if video_writer:
                    try:
                        video_writer.close()
                    except Exception as ex:
                        logger.warning("Error cerrando video writer: %s", ex)

                # 2. Calcular offset inicial entre video y audio
                offset_seconds = 0.0
                if (
                    compositor
                    and compositor.first_frame_time is not None
                    and mic_recorder
                    and mic_recorder.first_audio_time is not None
                ):
                    offset_seconds = compositor.first_frame_time - mic_recorder.first_audio_time
                    logger.info("Offset calculado A/V: %.4f segundos", offset_seconds)

                # 3. Muxing a MP4 final
                if temp_video is None or not temp_video.exists():
                    raise RuntimeError("No se encontró el archivo de video temporal para muxing.")

                if output_file is None:
                    raise RuntimeError("No se especificó la ruta del archivo de salida.")

                output_file.parent.mkdir(parents=True, exist_ok=True)

                success = muxer.mux(
                    video_path=temp_video,
                    audio_path=temp_audio,
                    output_mp4=output_file,
                    offset_seconds=offset_seconds,
                )

                self._cleanup_resources()

                if success and output_file.exists():
                    self.session_manager.transition_to(SessionState.DONE)
                    logger.info("Grabación completada: %s", output_file)
                    self.recording_finished.emit(output_file)
                else:
                    msg = "Error durante el muxing final de FFmpeg."
                    self.session_manager.transition_to(SessionState.ERROR, error_message=msg)
                    self.recording_failed.emit(msg)
            except Exception as e:
                logger.exception("Error crítico durante finalización de grabación: %s", e)
                self._cleanup_resources()
                self.session_manager.transition_to(SessionState.ERROR, error_message=str(e))
                self.recording_failed.emit(str(e))

        finalize_thread = threading.Thread(target=_finalize_worker, daemon=True, name="Finalize-Thread")
        finalize_thread.start()

    def _cleanup_resources(self) -> None:
        """Libera punteros y detiene componentes en ejecución si continúan activos."""
        if self._compositor:
            try:
                self._compositor.stop()
            except Exception:
                pass
        if self._capture_backend:
            try:
                self._capture_backend.stop()
            except Exception:
                pass
        if self._mic_recorder:
            try:
                self._mic_recorder.stop()
            except Exception:
                pass
        if self._video_writer:
            try:
                self._video_writer.close()
            except Exception:
                pass
        self._compositor = None
        self._video_writer = None
        self._capture_backend = None
        self._mic_recorder = None
