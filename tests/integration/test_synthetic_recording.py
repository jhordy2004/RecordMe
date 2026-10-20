"""Prueba de integración de grabación sintética: VideoWriter + WAV + Muxer a MP4."""

from pathlib import Path

import numpy as np
import soundfile as sf

from recordme.encode.muxer import Muxer
from recordme.encode.video_writer import VideoWriter


def test_synthetic_recording_pipeline(tmp_path: Path) -> None:
    """Genera video sintético y audio sintético, los combina y valida el MP4 resultante."""
    temp_video = tmp_path / "synthetic_video.mkv"
    temp_audio = tmp_path / "synthetic_audio.wav"
    output_mp4 = tmp_path / "final_output.mp4"

    width, height = 320, 240
    fps = 30
    duration_seconds = 2
    total_frames = fps * duration_seconds

    # 1. Escribir video sintético con patrón de colores cambiante
    writer = VideoWriter(
        output_file=temp_video,
        width=width,
        height=height,
        fps=fps,
    )
    started = writer.start()
    assert started is True

    for i in range(total_frames):
        # Frame de color dinámico
        frame = np.full((height, width, 3), (i % 255, (i * 2) % 255, 128), dtype=np.uint8)
        writer.write_frame(frame)

    frames_written = writer.close()
    assert frames_written == total_frames
    assert temp_video.exists()
    assert temp_video.stat().st_size > 0

    # 2. Escribir audio sintético (tono senoidal de 440 Hz)
    sample_rate = 48000
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    sine_wave = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    # Estéreo
    stereo_audio = np.column_stack((sine_wave, sine_wave))
    sf.write(str(temp_audio), stereo_audio, samplerate=sample_rate, subtype="PCM_16")
    assert temp_audio.exists()
    assert temp_audio.stat().st_size > 0

    # 3. Muxing a MP4
    muxer = Muxer()
    success = muxer.mux(
        video_path=temp_video,
        audio_path=temp_audio,
        output_mp4=output_mp4,
        offset_seconds=0.0,
    )
    assert success is True
    assert output_mp4.exists()
    assert output_mp4.stat().st_size > 1000
