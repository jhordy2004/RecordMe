"""Grabador de audio avanzado con soporte para micrófono, loopback del sistema y supresión de ruido."""

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


def _patch_soundcard_com() -> None:
    """Asegura compatibilidad COM en Windows para soundcard loopback."""
    import sys
    if sys.platform != "win32" or "soundcard.mediafoundation" in sys.modules:
        return
    try:
        from importlib.abc import MetaPathFinder
        from importlib.machinery import PathFinder

        class _SoundcardCOMFixer(MetaPathFinder):
            def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
                if fullname == "soundcard.mediafoundation":
                    spec = PathFinder.find_spec(fullname, path, target)
                    if spec and spec.loader:
                        orig_get_source = getattr(spec.loader, "get_source", None)
                        if orig_get_source:
                            src = orig_get_source(fullname)
                            src_fixed = src.replace(
                                "if hr + 2 ** 32 == RPC_E_CHANGED_MODE:",
                                "if hr + 2 ** 32 in (RPC_E_CHANGED_MODE, 0x100000001) or hr in (0, 1):",
                            ).replace(
                                "if self.com_loaded:",
                                "if getattr(self, 'com_loaded', False):",
                            )
                            spec.loader.get_source = lambda name: src_fixed
                            spec.loader.get_code = lambda name: compile(src_fixed, spec.origin, "exec")
                    return spec
                return None

        sys.meta_path.insert(0, _SoundcardCOMFixer())
    except Exception:
        pass


_patch_soundcard_com()


class MicRecorder:
    """Graba el audio del micrófono y opcionalmente el sonido del sistema (loopback de altavoces).

    Ofrece supresión inteligente de ruido con noisereduce, mezcla estéreo y soporte para mute/pausas.
    """

    def __init__(
        self,
        output_file: Path,
        device_index: int | None = None,
        samplerate: int = DEFAULT_AUDIO_SAMPLE_RATE,
        channels: int = DEFAULT_AUDIO_CHANNELS,
        mode: str = "mic_only",
        noise_reduction: bool = True,
        gain_db: float = 0.0,
    ) -> None:
        self.output_file = output_file
        self.device_index = device_index
        self.samplerate = samplerate
        self.channels = channels
        self.mode = mode
        self.noise_reduction = noise_reduction
        self.gain_db = gain_db

        # Archivos temporales para mezcla cuando se graba micrófono + sistema
        if self.mode == "mic_and_system":
            self._mic_file = output_file.with_name(f"{output_file.stem}_mic_raw.wav")
            self._sys_file = output_file.with_name(f"{output_file.stem}_sys_raw.wav")
        else:
            self._mic_file = output_file
            self._sys_file = None

        self._stream: sd.InputStream | None = None
        self._wav_file: sf.SoundFile | None = None
        self._queue: queue.Queue[npt.NDArray[np.float32] | None] = queue.Queue()
        self._writer_thread: threading.Thread | None = None
        self._sys_thread: threading.Thread | None = None

        self._is_recording = False
        self._recording_active = True
        self._is_paused = False
        self._is_muted = False
        self._first_audio_time: float | None = None
        self._lock = threading.Lock()
        self._peak_level: float = 0.0

        # Puerta de ruido inteligente en tiempo real
        self._gate_open: bool = False
        self._gate_hold_samples: int = 0
        self._gate_open_thresh: float = 0.018   # ~-35 dBFS (apertura ante voz de exposición)
        self._gate_close_thresh: float = 0.012  # ~-38 dBFS (cierre de histéresis)

    @property
    def first_audio_time(self) -> float | None:
        """Instante exacto (time.perf_counter) del primer bloque emitido a disco."""
        return self._first_audio_time

    @property
    def peak_level(self) -> float:
        """Nivel pico normalizado (0.0 a 1.0) para medidores de volumen en la UI."""
        return self._peak_level

    def set_recording_active(self, active: bool) -> None:
        """Controla si las muestras de audio deben persistirse en disco o descartarse (pre-warming durante cuenta atrás)."""
        self._recording_active = active
        if active and self._first_audio_time is None:
            self._first_audio_time = time.perf_counter()
        logger.debug("MicRecorder recording_active configurado a: %s", active)

    def set_muted(self, muted: bool) -> None:
        """Activa o desactiva el mute del micrófono. En modo muteado se escribe silencio para mantener sincronía."""
        self._is_muted = muted
        logger.info("Micrófono %s", "silenciado" if muted else "activo")

    def set_paused(self, paused: bool) -> None:
        """Pausa o reanuda la escritura de audio."""
        self._is_paused = paused
        logger.info("Grabación de audio %s", "pausada" if paused else "reanudada")

    def start(self) -> bool:
        """Inicia el stream de captura de audio y los hilos de escritura a disco."""
        try:
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            self._wav_file = sf.SoundFile(
                str(self._mic_file),
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

            # Si el modo incluye audio del sistema, iniciar captura loopback en hilo separado
            if self.mode == "mic_and_system" and self._sys_file is not None:
                self._sys_thread = threading.Thread(
                    target=self._system_audio_loop,
                    daemon=True,
                    name="Audio-SystemLoopbackThread",
                )
                self._sys_thread.start()

            logger.info(
                "MicRecorder iniciado: modo=%s, ruido=%s, salida=%s (%d Hz, %d ch)",
                self.mode,
                self.noise_reduction,
                self.output_file,
                self.samplerate,
                self.channels,
            )
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
        """Callback de sounddevice en tiempo real para micrófono."""
        if status:
            logger.debug("Estado de callback de audio: %s", status)

        if not self._is_recording or self._is_paused:
            return

        data = indata.copy()

        # Medir nivel pico en tiempo real para la interfaz gráfica y aplicar puerta de ruido inteligente
        peak = float(np.max(np.abs(data)))

        if self.noise_reduction and not self._is_muted:
            # Puerta de ruido en tiempo real (muta ruidos de fondo, golpes, corte de cuchillo, tecleo)
            if peak >= self._gate_open_thresh:
                self._gate_open = True
                self._gate_hold_samples = int(self.samplerate * 0.15)  # 150ms hold
            elif self._gate_hold_samples > 0:
                self._gate_hold_samples -= frames
            else:
                self._gate_open = False

            if not self._gate_open:
                # Puerta cerrada: atenuar completamente para entregar fondo negro puro
                data = np.zeros_like(data)
                self._peak_level = 0.0
            else:
                self._peak_level = peak
        else:
            self._peak_level = peak

        # Si aún estamos en modo de espera/cuenta regresiva, no guardar bloques aún
        if not self._recording_active:
            return

        with self._lock:
            if self._first_audio_time is None:
                self._first_audio_time = time.perf_counter()

        if self._is_muted:
            # Reemplazar con silencio para conservar la longitud temporal exacta
            data = np.zeros_like(data)
        elif self.gain_db != 0.0:
            gain_factor = 10.0 ** (self.gain_db / 20.0)
            data = np.clip(data * gain_factor, -1.0, 1.0)

        self._queue.put(data)

    def _system_audio_loop(self) -> None:
        """Hilo dedicado a capturar el audio del sistema mediante loopback WASAPI/soundcard de forma estable y continua."""
        if self._sys_file is None:
            return

        com_initialized = False
        try:
            import sys
            if sys.platform == "win32":
                try:
                    import ctypes
                    # 0x0 = COINIT_MULTITHREADED
                    res = ctypes.windll.ole32.CoInitializeEx(None, 0)
                    if res in (0, 1):
                        com_initialized = True
                except Exception:
                    pass

            import soundcard as sc

            speaker = sc.default_speaker()
            if speaker is None:
                logger.warning("No se encontró altavoz predeterminado para loopback del sistema.")
                return

            loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)
            if loopback is None:
                logger.warning("Dispositivo de loopback no disponible para %s.", speaker.name)
                return

            logger.info("Loopback del sistema inicializado en dispositivo: %s", loopback.name)

            # Cola desacoplada para evitar que la I/O de disco bloquee el buffer WASAPI
            sys_queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=1000)

            def _sys_writer_worker() -> None:
                try:
                    with sf.SoundFile(
                        str(self._sys_file),
                        mode="w",
                        samplerate=self.samplerate,
                        channels=2,
                        subtype="PCM_16",
                    ) as sys_wav:
                        while True:
                            try:
                                block = sys_queue.get(timeout=0.1)
                                if block is None:
                                    break
                                sys_wav.write(block)
                                sys_queue.task_done()
                            except queue.Empty:
                                if not self._is_recording and sys_queue.empty():
                                    break
                                continue
                except Exception as w_err:
                    logger.error("Error en hilo de escritura de audio del sistema: %s", w_err)

            writer_thread = threading.Thread(
                target=_sys_writer_worker,
                daemon=True,
                name="SysAudio-WriterThread",
            )
            writer_thread.start()

            # Asignar un búfer de 250ms (blocksize) para absorber picos de CPU/disco sin desbordar WASAPI
            buffer_frames = max(4800, int(self.samplerate * 0.25))

            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="data discontinuity in recording")
                    with loopback.recorder(samplerate=self.samplerate, channels=2, blocksize=buffer_frames) as rec:
                        while self._is_recording:
                            try:
                                # numframes=None entrega los frames listos directamente sin ceros artificiales
                                data = rec.record(numframes=None)
                                if not self._recording_active or self._is_paused:
                                    continue

                                if data is not None and len(data) > 0:
                                    # Normalizar valores anómalos para evitar chasquidos
                                    cleaned = np.nan_to_num(data, copy=False)
                                    np.clip(cleaned, -1.0, 1.0, out=cleaned)
                                    sys_queue.put(cleaned)
                            except Exception as loop_ex:
                                logger.debug("Aviso en bloque loopback (WASAPI): %s", loop_ex)
                                time.sleep(0.002)
            finally:
                sys_queue.put(None)
                writer_thread.join(timeout=3.0)
        except Exception as e:
            logger.warning("No se pudo iniciar la captura de audio del sistema (loopback): %s", e)
        finally:
            if com_initialized:
                try:
                    import ctypes
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass

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
        """Detiene la captura de audio, aplica reducción de ruido y mezcla las pistas si procede."""
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

        if self._sys_thread is not None and self._sys_thread.is_alive():
            self._sys_thread.join(timeout=2.0)
            self._sys_thread = None

        if self._wav_file is not None:
            try:
                self._wav_file.flush()
                self._wav_file.close()
            except Exception as e:
                logger.debug("Error cerrando archivo WAV: %s", e)
            finally:
                self._wav_file = None

        # 1. Aplicar supresión de ruido inteligente al micrófono si está activado
        if self.noise_reduction and self._mic_file.exists():
            self._apply_noise_reduction(self._mic_file)

        # 2. Si el modo es micrófono + sistema, mezclar ambos audios en el archivo final
        if self.mode == "mic_and_system" and self._sys_file is not None:
            self._mix_mic_and_system(self._mic_file, self._sys_file, self.output_file)

        logger.info("MicRecorder detenido exitosamente.")

    def _apply_noise_reduction(self, wav_path: Path) -> None:
        """Aplica procesamiento de audio profesional: filtro subsónico (80Hz), supresión espectral rápida y nivelación vocal."""
        try:
            import noisereduce as nr
            import scipy.signal as signal

            data, sr = sf.read(str(wav_path), dtype="float32")
            if len(data) > sr * 0.2:  # Al menos 200ms de audio grabado
                # 1. Filtro Butterworth pasaaltos a 80 Hz para eliminar zumbido eléctrico, ruidos de mesa y pop de respiración
                nyq = 0.5 * sr
                lowcut = 80.0 / nyq
                if 0 < lowcut < 1.0:
                    b, a = signal.butter(2, lowcut, btype="highpass")
                    data = signal.filtfilt(b, a, data, axis=0)

                # 2. Supresión de ruido espectral optimizada y suave (sin chirridos metálicos ni demoras prolongadas)
                is_multi = data.ndim > 1
                y_arr = data.T if is_multi else data
                # Perfil de ruido inicial de hasta 0.5s para estimación rápida
                noise_len = min(int(sr * 0.5), y_arr.shape[-1])
                y_noise = y_arr[:, :noise_len] if is_multi else y_arr[:noise_len]

                cleaned = nr.reduce_noise(
                    y=y_arr,
                    sr=sr,
                    y_noise=y_noise,
                    stationary=True,
                    prop_decrease=0.55,
                    n_fft=1024,
                    win_length=1024,
                )
                if is_multi:
                    cleaned = cleaned.T

                # 3. Normalización inteligente y limitador suave (solo si hay voz real; nunca amplificar siseo de fondo)
                max_peak = float(np.max(np.abs(cleaned)))
                if max_peak >= 0.08:  # Señal vocal real presente
                    target_peak = 10.0 ** (-1.0 / 20.0)  # ~0.891 (-1 dBFS)
                    gain = min(target_peak / max_peak, 5.5)  # Ganancia controlada para voz sin saturación
                    cleaned = np.clip(cleaned * gain, -1.0, 1.0)

                sf.write(str(wav_path), cleaned, sr, subtype="PCM_16")
                logger.info(
                    "Procesamiento de audio y supresión de ruido aplicados con éxito a %s (pico=%.2f)",
                    wav_path.name,
                    float(np.max(np.abs(cleaned))),
                )
        except Exception as e:
            logger.warning("Fallo al aplicar optimización de audio y supresión de ruido: %s", e)

    def _mix_mic_and_system(self, mic_path: Path, sys_path: Path, output_path: Path) -> None:
        """Mezcla armónicamente las pistas de micrófono y sonido del sistema en un único archivo WAV equilibrado."""
        try:
            if not mic_path.exists() and not sys_path.exists():
                return
            if not sys_path.exists() or sys_path.stat().st_size == 0:
                if mic_path != output_path and mic_path.exists():
                    mic_path.replace(output_path)
                return
            if not mic_path.exists() or mic_path.stat().st_size == 0:
                sys_path.replace(output_path)
                return

            mic_data, sr_mic = sf.read(str(mic_path), dtype="float32")
            sys_data, sr_sys = sf.read(str(sys_path), dtype="float32")

            # Normalizar a 2 canales estéreo
            if mic_data.ndim == 1:
                mic_data = np.column_stack([mic_data, mic_data])
            elif mic_data.shape[1] == 1:
                mic_data = np.repeat(mic_data, 2, axis=1)

            if sys_data.ndim == 1:
                sys_data = np.column_stack([sys_data, sys_data])
            elif sys_data.shape[1] == 1:
                sys_data = np.repeat(sys_data, 2, axis=1)

            # Igualar longitudes rellenando con silencio el más corto
            max_len = max(len(mic_data), len(sys_data))
            if len(mic_data) < max_len:
                mic_data = np.pad(mic_data, ((0, max_len - len(mic_data)), (0, 0)))
            if len(sys_data) < max_len:
                sys_data = np.pad(sys_data, ((0, max_len - len(sys_data)), (0, 0)))

            mic_peak = float(np.max(np.abs(mic_data)))
            sys_peak = float(np.max(np.abs(sys_data)))

            # Si el micrófono sólo captó ruido/sangrado de fondo bajo (< 0.06)
            # y el sistema tiene audio real, preservar la pista del sistema pura para 0 interferencias
            if mic_peak < 0.06 and sys_peak >= 0.005:
                mixed = sys_data
                logger.info("Micrófono silencioso/ambiente (pico=%.3f): audio del sistema puro preservado.", mic_peak)
            elif sys_peak < 0.005 and mic_peak >= 0.005:
                mixed = mic_data
            else:
                # Mezcla armónica: voz clara al frente y sistema equilibrado con headroom natural
                mixed = (mic_data * 0.85) + (sys_data * 0.70)
                peak = float(np.max(np.abs(mixed)))
                if peak > 0.95:
                    mixed = (mixed / peak) * 0.95

            peak = float(np.max(np.abs(mixed)))
            sf.write(str(output_path), mixed, self.samplerate, subtype="PCM_16")
            logger.info("Mezcla de micrófono y audio del sistema completada: %s (pico=%.2f)", output_path.name, peak)

            # Limpiar archivos temporales
            if mic_path != output_path:
                mic_path.unlink(missing_ok=True)
            sys_path.unlink(missing_ok=True)
        except Exception as e:
            logger.exception("Error durante la mezcla de audio: %s", e)
            if mic_path.exists() and mic_path != output_path:
                mic_path.replace(output_path)
                mic_path.unlink(missing_ok=True)
            sys_path.unlink(missing_ok=True)
