"""Recursos estáticos y modelos de RecordMe."""

import ctypes
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

logger = logging.getLogger(__name__)


def setup_app_user_model_id() -> None:
    """Configura el identificador de modelo de usuario en Windows para fijar icono en barra de tareas."""
    if sys.platform == "win32":
        try:
            myappid = "recordme.app.recorder.1.0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            logger.debug("No se pudo establecer SetCurrentProcessExplicitAppUserModelID: %s", e)


def get_app_icon() -> QIcon:
    """Carga y construye el icono de la aplicación combinando todas las resoluciones disponibles.

    Las resoluciones son 16x16, 24x24, 32x32, 48x48, 64x64, 128x128 y 256x256.
    """
    icon = QIcon()
    search_dirs = [
        Path(__file__).resolve().parent / "ico",
        Path(__file__).resolve().parent.parent.parent / "ico",  # src/ico
        Path("src/ico"),
    ]
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        search_dirs.extend([
            base / "recordme" / "resources" / "ico",
            base / "resources" / "ico",
            base / "ico",
            Path(sys.executable).parent / "resources" / "ico",
            Path(sys.executable).parent / "ico",
        ])

    sizes = [16, 24, 32, 48, 64, 128, 256]
    for directory in search_dirs:
        if directory.exists():
            for s in sizes:
                ico_path = directory / f"icono_{s}.ico"
                if ico_path.exists():
                    icon.addFile(str(ico_path), QSize(s, s))
            if not icon.isNull():
                break

    return icon
