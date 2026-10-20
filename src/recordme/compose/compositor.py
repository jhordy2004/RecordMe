"""Compositor de video en tiempo real: reloj de frames, recorte y encause al VideoWriter."""

import logging
import threading
import time

import cv2
import numpy as np
import numpy.typing as npt

from recordme.camera.camera_source import CameraSource
from recordme.capture.base import CaptureBackend
from recordme.compose.camera_layer import CameraLayer
from recordme.compose.censor_layer import CensorLayer
from recordme.compose.zoom_layer import ZoomLayer
from recordme.core.render_state import RenderState
from recordme.encode.video_writer import VideoWriter

logger = logging.getLogger(__name__)


class Compositor:
    """Ejecuta el ciclo de reloj de fotogramas, lee la pantalla y emite al VideoWriter."""

    def __init__(
        self,
        capture_backend: CaptureBackend,
        video_writer: VideoWriter,
        initial_render_state: RenderState,
        camera_source: CameraSource | None = None,
        fps: int = 30,
    ) -> None:
        self.capture_backend = capture_backend
        self.video_writer = video_writer
        self.camera_source = camera_source
        self._fps = fps
        self._frame_interval = 1.0 / max(1, fps)

        self._render_state = initial_render_state
        self._state_lock = threading.Lock()
        self._camera_layer = CameraLayer()
        self._censor_layer = CensorLayer()
        self._zoom_layer = ZoomLayer(tau_seconds=0.20)
        self._last_frame_time: float = time.perf_counter()

        self._is_running = False
        self._is_paused = False
        self._thread: threading.Thread | None = None

        self._first_frame_time: float | None = None
        self._total_frames_composed = 0
        self._last_valid_frame: npt.NDArray[np.uint8] | None = None

    @property
    def first_frame_time(self) -> float | None:
        """Instante exacto (time.perf_counter) en que se emitió el primer fotograma."""
        return self._first_frame_time

    @property
    def total_frames(self) -> int:
        """Número total de frames procesados."""
        return self._total_frames_composed

    def update_render_state(self, state: RenderState) -> None:
        """Actualiza atómicamente el snapshot de estado que consume el compositor."""
        with self._state_lock:
            self._render_state = state

    def set_paused(self, paused: bool) -> None:
        """Pausa o reanuda la emisión de frames."""
        self._is_paused = paused

    def start(self) -> None:
        """Inicia el hilo del compositor."""
        self._is_running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="Compositor-Thread")
        self._thread.start()
        logger.info("Compositor iniciado a %d FPS.", self._fps)

    def _loop(self) -> None:
        """Bucle de alta precisión temporal con compensación de frames perdidos."""
        t0 = time.perf_counter()
        iteration = 0
        paused_duration = 0.0
        pause_start_time: float | None = None
        consecutive_duplicates = 0

        while self._is_running:
            now = time.perf_counter()

            if self._is_paused:
                if pause_start_time is None:
                    pause_start_time = now
                time.sleep(0.01)
                continue
            else:
                if pause_start_time is not None:
                    # Acumular el tiempo pausado para no saltar en el reloj
                    paused_duration += now - pause_start_time
                    pause_start_time = None

            target_time = t0 + paused_duration + (iteration * self._frame_interval)
            wait_time = target_time - now

            if wait_time > 0.001:
                time.sleep(wait_time * 0.75)  # Dormir la mayor parte
                while time.perf_counter() < target_time:
                    pass  # Espera activa para precisión de microsegundos

            # Capturar y componer frame
            frame = self._compose_frame()
            if frame is not None:
                if self._first_frame_time is None:
                    self._first_frame_time = time.perf_counter()
                self.video_writer.write_frame(frame)
                self._total_frames_composed += 1
                consecutive_duplicates = 0
            elif self._last_valid_frame is not None:
                # Duplicar último frame si hay retraso de captura (máximo 5 seguidos)
                if consecutive_duplicates < 5:
                    self.video_writer.write_frame(self._last_valid_frame)
                    self._total_frames_composed += 1
                    consecutive_duplicates += 1

            iteration += 1

    def _compose_frame(self) -> npt.NDArray[np.uint8] | None:
        """Extrae el fotograma de la pantalla y aplica el recorte del área con preservación exacta."""
        with self._state_lock:
            state = self._render_state

        raw_frame = self.capture_backend.get_latest_frame()
        if raw_frame is None:
            return None

        target_w = state.output_width
        target_h = state.output_height

        # Caso 1: El frame ya viene con el tamaño exacto de la región capturada
        if raw_frame.shape[1] == target_w and raw_frame.shape[0] == target_h:
            composed = raw_frame
        # Caso 2: El frame es la pantalla completa (dimensiones mayores que contienen la región)
        elif (
            raw_frame.shape[1] >= state.capture_region.x + target_w
            and raw_frame.shape[0] >= state.capture_region.y + target_h
        ):
            rx = state.capture_region.x
            ry = state.capture_region.y
            composed = raw_frame[ry : ry + target_h, rx : rx + target_w]
        else:
            # Caso 3: Discrepancia menor (por redondeo de 1 o 2 px en backend o límites de pantalla)
            resized: npt.NDArray[np.uint8] = np.asarray(
                cv2.resize(raw_frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR),
                dtype=np.uint8,
            )
            composed = resized

        now = time.perf_counter()
        dt = now - self._last_frame_time
        self._last_frame_time = now

        # 1. Censura en tiempo real (antes del zoom)
        if state.censor_regions:
            composed = self._censor_layer.render(composed, state.censor_regions, state.capture_region)

        # 2. Zoom cinemático continuo con suavizado exponencial
        composed = self._zoom_layer.render(
            frame=composed,
            target_zoom=state.target_zoom,
            target_cx=state.target_center_x,
            target_cy=state.target_center_y,
            dt=dt,
        )

        # 3. Superponer capa de cámara si está activada (después del zoom)
        if state.camera.enabled and self.camera_source is not None:
            cam_frame = self.camera_source.get_latest_frame()
            if cam_frame is not None:
                composed = composed.copy()
                composed = self._camera_layer.render(composed, cam_frame, state.camera)

        self._last_valid_frame = composed
        return composed

    def stop(self) -> None:
        """Detiene el hilo del compositor."""
        self._is_running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Compositor detenido. Total fotogramas compuestos: %d", self._total_frames_composed)
