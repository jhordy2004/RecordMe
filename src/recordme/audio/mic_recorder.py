"""Grabador de audio de micrófono a archivo temporal WAV usando sounddevice y soundfile."""

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import sounddevice as sd
import soundfile as sf

from recordme.constants import DEFAULT_AUDIO_CHANNELS, DEFAULT_AUDIO_SAMPLE_RATE

logger = logging.getLogger(__name__)


class MicRecorder:
    """Graba el audio del micrófono en un archivo WAV con soporte para mute (relleno con ceros) y pausas."""

    def __init__(
        self,
        output_file: Path,
        device_index: int | None = None,
        samplerate: int = DEFAULT_AUDIO_SAMPLE_RATE,
        channels: int = DEFAULT_AUDIO_CHANNELS,
    ) -> None:
        self.output_file = output_file
        self.device_index = device_index
        self.samplerate = samplerate
        self.channels = channels

        self._stream: sd.InputStream | None = None
        self._wav_file: sf.SoundFile | None = None
        self._queue: queue.Queue[npt.NDArray[np.float32] | None] = queue.Queue()
        self._writer_thread: threading.Thread | None = None

        self._is_recording = False
        self._is_paused = False
        self._is_muted = False
        self._first_audio_time: float | None = None
        self._lock = threading.Lock()
        self._peak_level: float = 0.0

    @property
    def first_audio_time(self) -> float | None:
        """Instante exacto (time.perf_counter) del primer bloque recibido."""
        return self._first_audio_time

    @property
    def peak_level(self) -> float:
        """Nivel pico normalizado (0.0 a 1.0) para medidores de volumen en la UI."""
        return self._peak_level

    def set_muted(self, muted: bool) -> None:
        """Activa o desactiva el mute. Cuando está muteado se escribe silencio para mantener sincronía."""
        self._is_muted = muted
        logger.info("Micrófono %s", "silenciado" if muted else "activo")

    def set_paused(self, paused: bool) -> None:
        """Pausa o reanuda la escritura de audio."""
        self._is_paused = paused
        logger.info("Grabación de audio %s", "pausada" if paused else "reanudada")

    def start(self) -> bool:
        """Inicia el stream de captura de audio y el hilo de escritura a disco."""
        try:
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            self._wav_file = sf.SoundFile(
                str(self.output_file),
                mode="w",
                samplerate=self.samplerate,
                channels=self.channels,
                subtype="PCM_16",
            )

            self._is_recording = True
            self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True, name="Audio-WriterThread")
            self._writer_thread.start()

            self._stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                device=self.device_index,
                callback=self._audio_callback,
                dtype="float32",
            )
            self._stream.start()
            logger.info("MicRecorder iniciado en %s (%d Hz, %d ch)", self.output_file, self.samplerate, self.channels)
            return True
        except Exception as e:
            logger.exception("Error al iniciar MicRecorder: %s", e)
            self.stop()
            return False

    def _audio_callback(
        self,
        indata: npt.NDArray[np.float32],
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        """Callback de sounddevice en tiempo real."""
        if status:
            logger.debug("Estado de callback de audio: %s", status)

        if not self._is_recording or self._is_paused:
            return

        with self._lock:
            if self._first_audio_time is None:
                self._first_audio_time = time.perf_counter()

        data = indata.copy()

        # Medir nivel pico
        try:
            self._peak_level = float(np.max(np.abs(data)))
        except Exception:
            self._peak_level = 0.0

        if self._is_muted:
            # Reemplazar con silencio para conservar la longitud temporal exacta
            data = np.zeros_like(data)

        self._queue.put(data)

    def _writer_loop(self) -> None:
        """Hilo dedicado a escribir bloques de audio en el archivo WAV."""
        while self._is_recording or not self._queue.empty():
            try:
                block = self._queue.get(timeout=0.1)
                if block is None:
                    break
                if self._wav_file is not None:
                    self._wav_file.write(block)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error("Error escribiendo bloque de audio: %s", e)

    def stop(self) -> None:
        """Detiene la captura de audio y cierra el archivo WAV."""
        self._is_recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug("Error cerrando stream de audio: %s", e)
            finally:
                self._stream = None

        # Señalizar fin al hilo de escritura
        self._queue.put(None)
        if self._writer_thread is not None and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2.0)
            self._writer_thread = None

        if self._wav_file is not None:
            try:
                self._wav_file.flush()
                self._wav_file.close()
            except Exception as e:
                logger.debug("Error cerrando archivo WAV: %s", e)
            finally:
                self._wav_file = None

        logger.info("MicRecorder detenido exitosamente.")
