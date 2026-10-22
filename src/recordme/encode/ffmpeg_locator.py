"""Localizador del ejecutable de FFmpeg."""

import logging
import os
import shutil
import sys
from pathlib import Path

import imageio_ffmpeg

logger = logging.getLogger(__name__)


def get_ffmpeg_exe() -> str:
    """Devuelve la ruta ejecutable a FFmpeg, priorizando bundle congelado, imageio-ffmpeg o PATH."""
    # 0. Probar directorio empaquetado PyInstaller (sys._MEIPASS) o directorio del ejecutable
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates = [
            base_dir / "imageio_ffmpeg" / "binaries",
            base_dir / "binaries",
            base_dir,
            Path(sys.executable).parent,
            Path(sys.executable).parent / "imageio_ffmpeg" / "binaries",
        ]
        for c in candidates:
            if c.exists():
                for pattern in ("ffmpeg*.exe", "ffmpeg*"):
                    found = [f for f in c.glob(pattern) if f.is_file() and not f.name.startswith("ffprobe")]
                    if found:
                        logger.debug("FFmpeg detectado en bundle congelado: %s", found[0])
                        return str(found[0])

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
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates = [
            base_dir / "imageio_ffmpeg" / "binaries",
            base_dir / "binaries",
            base_dir,
            Path(sys.executable).parent,
        ]
        for c in candidates:
            if c.exists():
                for pattern in ("ffprobe*.exe", "ffprobe*"):
                    found = [f for f in c.glob(pattern) if f.is_file()]
                    if found:
                        return str(found[0])

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
