"""Localizador del ejecutable de FFmpeg."""

import logging
import os
import shutil
from pathlib import Path

import imageio_ffmpeg

logger = logging.getLogger(__name__)


def get_ffmpeg_exe() -> str:
    """Devuelve la ruta ejecutable a FFmpeg, priorizando imageio-ffmpeg o el PATH del sistema."""
    # 1. Probar imageio-ffmpeg
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            logger.debug("FFmpeg detectado vía imageio-ffmpeg: %s", exe)
            return str(exe)
    except Exception as e:
        logger.debug("Error obteniendo FFmpeg de imageio-ffmpeg: %s", e)

    # 2. Probar PATH del sistema
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        logger.debug("FFmpeg detectado en el PATH del sistema: %s", system_ffmpeg)
        return system_ffmpeg

    # 3. Default a 'ffmpeg'
    return "ffmpeg"


def get_ffprobe_exe() -> str:
    """Devuelve la ruta ejecutable a FFprobe o al del sistema."""
    system_ffprobe = shutil.which("ffprobe")
    if system_ffprobe:
        return system_ffprobe

    # Derivar del directorio de imageio_ffmpeg si existe
    try:
        ffmpeg_exe = Path(get_ffmpeg_exe())
        sibling_ffprobe = ffmpeg_exe.parent / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if sibling_ffprobe.exists():
            return str(sibling_ffprobe)
    except Exception:
        pass

    return "ffprobe"
