"""Escritor de video mediante pipe stdin a subproceso FFmpeg hacia archivo temporal MKV."""

import logging
import subprocess
import threading
from pathlib import Path

import numpy as np
import numpy.typing as npt

from recordme.encode.ffmpeg_locator import get_ffmpeg_exe
from recordme.utils.geometry import Rect

logger = logging.getLogger(__name__)


class VideoWriter:
    """Administra el subproceso de FFmpeg para codificar frames BGR crudos a un archivo MKV."""

    def __init__(
        self,
        output_file: Path,
        width: int,
        height: int,
        fps: int = 30,
        crf: int = 20,
        preset: str = "veryfast",
    ) -> None:
        self.output_file = output_file
        # Asegurar dimensiones pares requeridas por yuv420p
        even_rect = Rect(x=0, y=0, width=width, height=height).to_even()
        self.width = even_rect.width
        self.height = even_rect.height
        self.fps = fps
        self.crf = crf
        self.preset = preset

        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._frames_written = 0
        self._is_open = False

    def start(self) -> bool:
        """Inicia el subproceso FFmpeg."""
        ffmpeg_bin = get_ffmpeg_exe()
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{self.width}x{self.height}",
            "-r",
            str(self.fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            self.preset,
            "-crf",
            str(self.crf),
            "-pix_fmt",
            "yuv420p",
            "-g",
            str(self.fps * 2),
            str(self.output_file),
        ]

        logger.info("Lanzando FFmpeg: %s", " ".join(cmd))
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                bufsize=10**7,
            )
            self._is_open = True
            self._frames_written = 0
            return True
        except Exception as e:
            logger.exception("Error iniciando subproceso FFmpeg: %s", e)
            self._is_open = False
            return False

    def write_frame(self, frame: npt.NDArray[np.uint8]) -> bool:
        """Escribe un frame en el pipe stdin de FFmpeg."""
        if not self._is_open or self._process is None or self._process.stdin is None:
            return False

        try:
            # Asegurar forma y dimensiones correctas
            if frame.shape[0] != self.height or frame.shape[1] != self.width:
                import cv2
                frame = np.asarray(
                    cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR),
                    dtype=np.uint8,
                )

            data = frame.tobytes()
            with self._lock:
                self._process.stdin.write(data)
                self._frames_written += 1
            return True
        except (BrokenPipeError, OSError) as e:
            logger.error("Pipe de FFmpeg cerrado inesperadamente: %s", e)
            self._is_open = False
            return False
        except Exception as e:
            logger.exception("Error escribiendo frame a FFmpeg: %s", e)
            return False

    def close(self) -> int:
        """Cierra el pipe stdin de FFmpeg y espera la finalización del proceso."""
        if not self._is_open or self._process is None:
            return self._frames_written

        logger.info("Cerrando VideoWriter... Total frames escritos: %d", self._frames_written)
        self._is_open = False
        try:
            if self._process.stdin:
                try:
                    self._process.stdin.flush()
                    self._process.stdin.close()
                except Exception:
                    pass
            stderr_out = b""
            if self._process.stderr:
                stderr_out = self._process.stderr.read()
            self._process.wait(timeout=10.0)
            if self._process.returncode != 0:
                logger.warning(
                    "FFmpeg terminó con código %d. Detalle: %s",
                    self._process.returncode,
                    stderr_out.decode("utf-8", errors="replace"),
                )
        except Exception as e:
            logger.warning("Error cerrando proceso FFmpeg: %s. Forzando terminación.", e)
            try:
                self._process.kill()
            except Exception:
                pass
        finally:
            self._process = None

        return self._frames_written
