"""Gestión de rutas del sistema utilizando platformdirs."""

from pathlib import Path

import platformdirs

from recordme.constants import APP_NAME, ORGANIZATION_NAME


def get_config_dir() -> Path:
    """Devuelve el directorio de configuración del usuario."""
    path = Path(platformdirs.user_config_dir(appname=APP_NAME, appauthor=ORGANIZATION_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_dir() -> Path:
    """Devuelve el directorio de datos del usuario (ej. guiones de teleprompter)."""
    path = Path(platformdirs.user_data_dir(appname=APP_NAME, appauthor=ORGANIZATION_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_dir() -> Path:
    """Devuelve el directorio de logs de la aplicación."""
    path = Path(platformdirs.user_log_dir(appname=APP_NAME, appauthor=ORGANIZATION_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_temp_dir() -> Path:
    """Devuelve un directorio temporal propio para grabaciones en curso."""
    path = Path(platformdirs.user_cache_dir(appname=APP_NAME, appauthor=ORGANIZATION_NAME)) / "temp_recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_default_recordings_dir() -> Path:
    """Devuelve la carpeta por defecto de videos/grabaciones."""
    videos_dir = platformdirs.user_videos_dir()
    if not videos_dir:
        path = Path.home() / "Videos" / APP_NAME
    else:
        path = Path(videos_dir) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_scripts_dir() -> Path:
    """Devuelve la carpeta de guiones para el teleprompter."""
    path = get_data_dir() / "scripts"
    path.mkdir(parents=True, exist_ok=True)
    return path
