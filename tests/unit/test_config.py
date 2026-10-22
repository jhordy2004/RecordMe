"""Pruebas unitarias para el sistema de configuración."""

import json
from pathlib import Path

from recordme.config.settings import AppSettings


def test_default_settings() -> None:
    """Verifica que la configuración por defecto tenga valores válidos."""
    settings = AppSettings()
    assert settings.language == "auto"
    assert settings.output.fps == 30
    assert settings.audio.mic_enabled is True
    assert settings.camera.enabled is False
    assert settings.teleprompter.wpm == 130


def test_save_and_load_settings(tmp_path: Path) -> None:
    """Verifica el ciclo de guardado y recarga de configuración."""
    config_file = tmp_path / "settings.json"
    settings = AppSettings()
    settings.output.fps = 60
    settings.teleprompter.wpm = 160
    settings.save(config_file)

    loaded = AppSettings.load(config_file)
    assert loaded.output.fps == 60
    assert loaded.teleprompter.wpm == 160


def test_corrupted_json_fallback(tmp_path: Path) -> None:
    """Verifica que un JSON corrupto no cause un crash y se use la configuración por defecto."""
    config_file = tmp_path / "settings.json"
    config_file.write_text("{ esto no es un json valido :", encoding="utf-8")

    loaded = AppSettings.load(config_file)
    assert loaded.output.fps == 30
    assert loaded.language == "auto"


def test_partial_json_fallback(tmp_path: Path) -> None:
    """Verifica que un JSON parcial complete los campos faltantes con valores por defecto."""
    config_file = tmp_path / "settings.json"
    partial_data = {"output": {"fps": 24}}
    config_file.write_text(json.dumps(partial_data), encoding="utf-8")

    loaded = AppSettings.load(config_file)
    assert loaded.output.fps == 24
    assert loaded.output.quality == "high"
    assert loaded.camera.size_pct == 18
