"""Compositor de video en tiempo real: reloj de frames, recorte y encause al VideoWriter."""

import logging
import threading
import time

import numpy as np
import numpy.typing as npt

from recordme.capture.base import CaptureBackend
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
        fps: int = 30,
    ) -> None:
        self.capture_backend = capture_backend
        self.video_writer = video_writer
        self._fps = fps
        self._frame_interval = 1.0 / max(1, fps)

        self._render_state = initial_render_state
        self._state_lock = threading.Lock()

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
        """Extrae el fotograma de la pantalla y aplica el recorte del área."""
        with self._state_lock:
            state = self._render_state

        raw_frame = self.capture_backend.get_latest_frame()
        if raw_frame is None:
            return None

        # Si el backend no recortó internamente, recortar aquí
        h, w = raw_frame.shape[:2]
        crop_x = max(0, min(state.capture_region.x, w - 2))
        crop_y = max(0, min(state.capture_region.y, h - 2))
        crop_w = max(2, min(state.capture_region.width, w - crop_x))
        crop_h = max(2, min(state.capture_region.height, h - crop_y))

        # Asegurar par
        crop_w = crop_w if crop_w % 2 == 0 else crop_w - 1
        crop_h = crop_h if crop_h % 2 == 0 else crop_h - 1

        # Si el frame ya viene del tamaño de la región (como en dxcam con region)
        if raw_frame.shape[1] == crop_w and raw_frame.shape[0] == crop_h:
            composed = raw_frame
        elif raw_frame.shape[1] >= crop_x + crop_w and raw_frame.shape[0] >= crop_y + crop_h:
            composed = raw_frame[crop_y : crop_y + crop_h, crop_x : crop_x + crop_w]
        else:
            composed = raw_frame

        self._last_valid_frame = composed
        return composed

    def stop(self) -> None:
        """Detiene el hilo del compositor."""
        self._is_running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Compositor detenido. Total fotogramas compuestos: %d", self._total_frames_composed)
