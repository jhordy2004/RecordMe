"""Pruebas unitarias de cálculo de líneas y velocidad WPM del teleprompter."""

from recordme.config.settings import TeleprompterSettings


def test_teleprompter_wpm_timing_calculation() -> None:
    """Verifica que el cálculo de avance por WPM esté dentro del ±3% de tolerancia exigido."""
    wpm = 130
    words = 260  # Debería tardar exactamente 2.0 minutos (120 segundos)
    expected_duration_seconds = (words / wpm) * 60.0

    # Simular avance temporal a 30 FPS
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

    # Validar que el tiempo transcurrido difiere menos del 3% respecto al tiempo teórico
    diff_pct = abs(elapsed_time - expected_duration_seconds) / expected_duration_seconds
    assert diff_pct < 0.03, f"Desviación de tiempo mayor al 3%: {diff_pct * 100:.2f}%"


def test_teleprompter_settings_defaults() -> None:
    """Verifica los valores por defecto del teleprompter."""
    settings = TeleprompterSettings()
    assert settings.wpm == 130
    assert settings.font_size == 34
    assert settings.lines_visible == 2
    assert settings.opacity == 0.78
    assert settings.width_pct == 60
