"""Configuración de logging con rotación y salida a consola."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from recordme.config.paths import get_log_dir
from recordme.constants import APP_NAME

LOG_FILENAME = f"{APP_NAME.lower()}.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3


def setup_logging(debug: bool = False) -> logging.Logger:
    """Configura el sistema de registro global para RecordMe."""
    log_dir = get_log_dir()
    log_file = log_dir / LOG_FILENAME

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Limpiar manejadores previos si existen
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler de archivo con rotación
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    root_logger.addHandler(file_handler)

    # Handler de consola (solo si stdout está conectado a una consola real)
    if sys.stdout is not None:
        try:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
            root_logger.addHandler(console_handler)
        except Exception:
            pass

    logger = logging.getLogger(APP_NAME)
    logger.info("Sistema de logging inicializado. Archivo de log: %s", log_file)
    return logger
