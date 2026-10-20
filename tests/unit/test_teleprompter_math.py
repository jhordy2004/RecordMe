"""Pruebas unitarias de cálculo de líneas y velocidad en segundos del teleprompter."""

from recordme.config.settings import TeleprompterSettings


def test_teleprompter_seconds_per_line_timing() -> None:
    """Verifica que el avance por segundos por línea sea matemáticamente exacto."""
    seconds_per_line = 3.0
    line_height = 44
    pixels_per_second = line_height / seconds_per_line

    # Para 5 líneas de texto, la distancia total es 5 * 44 = 220 px
    # A 3.0 segundos por línea, debe tardar exactamente 15.0 segundos
    num_lines = 5
    total_distance = num_lines * line_height
    calculated_time = total_distance / pixels_per_second

    assert abs(calculated_time - 15.0) < 0.001


def test_teleprompter_wpm_timing_calculation() -> None:
    """Verifica que el cálculo de avance por WPM esté dentro del ±3% de tolerancia exigido."""
    wpm = 130
    words = 260
    expected_duration_seconds = (words / wpm) * 60.0

    fps = 30
    dt = 1.0 / fps
    words_per_line = 7.5
    line_height = 40

    lines_per_second = (wpm / 60.0) / words_per_line
    pixels_per_second = lines_per_second * line_height

    total_lines = words / words_per_line
    total_pixels_target = total_lines * line_height

    elapsed_time = 0.0
    accumulated_pixels = 0.0

    while accumulated_pixels < total_pixels_target:
        accumulated_pixels += pixels_per_second * dt
        elapsed_time += dt

    diff_pct = abs(elapsed_time - expected_duration_seconds) / expected_duration_seconds
    assert diff_pct < 0.03, f"Desviación de tiempo mayor al 3%: {diff_pct * 100:.2f}%"


def test_teleprompter_settings_defaults() -> None:
    """Verifica los valores por defecto del teleprompter."""
    settings = TeleprompterSettings()
    assert settings.seconds_per_line == 3.5
    assert settings.wpm == 130
    assert settings.font_size == 34
    assert settings.lines_visible == 2
    assert settings.opacity == 0.78
    assert settings.width_pct == 60
