"""Módulo de configuración y rutas de RecordMe."""

from recordme.config.paths import (
    get_config_dir,
    get_data_dir,
    get_default_recordings_dir,
    get_log_dir,
    get_scripts_dir,
    get_temp_dir,
)
from recordme.config.settings import AppSettings

__all__ = [
    "AppSettings",
    "get_config_dir",
    "get_data_dir",
    "get_default_recordings_dir",
    "get_log_dir",
    "get_scripts_dir",
    "get_temp_dir",
]
