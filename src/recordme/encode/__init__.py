"""Módulo de codificación de video y audio con FFmpeg."""

from recordme.encode.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from recordme.encode.muxer import Muxer
from recordme.encode.video_writer import VideoWriter

__all__ = ["Muxer", "VideoWriter", "get_ffmpeg_exe", "get_ffprobe_exe"]
