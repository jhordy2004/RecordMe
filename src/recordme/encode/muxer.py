"""Muxer final para combinar video MKV y audio WAV en MP4 con sincronización exacta."""

import logging
import subprocess
from pathlib import Path

from recordme.encode.ffmpeg_locator import get_ffmpeg_exe

logger = logging.getLogger(__name__)


class Muxer:
    """Combina streams de video y audio con corrección de desfase temporal inicial."""

    def __init__(self, ffmpeg_bin: str | None = None) -> None:
        self.ffmpeg_bin = ffmpeg_bin or get_ffmpeg_exe()

    def mux(
        self,
        video_path: Path,
        audio_path: Path | None,
        output_mp4: Path,
        offset_seconds: float = 0.0,
        keep_temp_on_error: bool = True,
    ) -> bool:
        """Mezcla video y audio en un MP4 final optimizado para streaming web (+faststart)."""
        output_mp4.parent.mkdir(parents=True, exist_ok=True)

        if audio_path is not None and audio_path.exists() and audio_path.stat().st_size > 100:
            # Comando con audio y corrección de offset
            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-i",
                str(video_path),
                "-itsoffset",
                f"{offset_seconds:.4f}",
                "-i",
                str(audio_path),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-af",
                "aresample=async=1",
                "-movflags",
                "+faststart",
                str(output_mp4),
            ]
        else:
            # Solo video
            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-i",
                str(video_path),
                "-c:v",
                "copy",
                "-movflags",
                "+faststart",
                str(output_mp4),
            ]

        logger.info("Ejecutando Muxer: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=False,
                timeout=60.0,
            )
            if result.returncode == 0 and output_mp4.exists() and output_mp4.stat().st_size > 0:
                logger.info("Muxer finalizado exitosamente: %s (tamaño: %d bytes)", output_mp4, output_mp4.stat().st_size)
                # Limpiar temporales si el usuario lo desea
                try:
                    if video_path.exists():
                        video_path.unlink()
                    if audio_path is not None and audio_path.exists():
                        audio_path.unlink()
                except Exception as e:
                    logger.debug("No se pudieron eliminar temporales: %s", e)
                return True
            else:
                stderr_text = result.stderr.decode("utf-8", errors="replace")
                logger.error("Error en FFmpeg muxer (código %d): %s", result.returncode, stderr_text)
                if keep_temp_on_error:
                    logger.warning("Archivos temporales conservados en: %s, %s", video_path, audio_path)
                return False
        except Exception as e:
            logger.exception("Excepción durante el proceso de muxing: %s", e)
            return False
