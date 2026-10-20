"""Punto de entrada de la aplicación RecordMe, inicialización de Qt y servicios."""

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from recordme.config.settings import AppSettings
from recordme.constants import APP_DISPLAY_NAME, APP_NAME, APP_VERSION
from recordme.core.session import SessionManager
from recordme.platform_services.factory import get_platform_services
from recordme.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def apply_dark_theme(app: QApplication) -> None:
    """Aplica una paleta oscura moderna consistente a toda la aplicación Qt."""
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.Base, QColor(20, 20, 20))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Text, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    app.setPalette(palette)


class WelcomeWindow(QMainWindow):
    """Ventana inicial de comprobación de cimientos (Fase 0)."""

    def __init__(self, session_manager: SessionManager, settings: AppSettings) -> None:
        super().__init__()
        self.session_manager = session_manager
        self.settings = settings
        self.platform_services = get_platform_services()

        self.setWindowTitle(f"{APP_DISPLAY_NAME} v{APP_VERSION}")
        self.setMinimumSize(480, 260)
        self.resize(520, 300)

        # Contenedor central
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Título
        title_label = QLabel(f"Bienvenido a {APP_NAME}")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Subtítulo descriptivo
        desc_label = QLabel(
            "Cimientos de arquitectura inicializados correctamente.\n"
            "Grabador de pantalla con cámara, zoom en vivo, censura y teleprompter."
        )
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Estado del sistema
        info_label = QLabel(
            f"• SO: {sys.platform}\n"
            f"• Carpeta de guardado: {self.settings.output.folder}\n"
            f"• Estado de sesión: {self.session_manager.state.name}"
        )
        info_label.setStyleSheet("color: #AAAAAA; font-size: 12px; margin-top: 8px;")
        layout.addWidget(info_label)

        layout.addStretch()

        # Botones de acción
        btn_layout = QHBoxLayout()
        self.status_btn = QPushButton("Comprobar Servicios")
        self.status_btn.clicked.connect(self._check_services)
        btn_layout.addWidget(self.status_btn)

        self.close_btn = QPushButton("Cerrar")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def _check_services(self) -> None:
        """Verifica la invocación a los servicios de plataforma."""
        excluded = self.platform_services.exclude_window_from_capture(self)
        logger.info("Comprobación de exclusión de captura: %s", excluded)
        self.status_btn.setText(f"Exclusión captura: {'OK' if excluded else 'No compatible'}")

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Aplica la exclusión de captura y estilos nativos una vez mostrada la ventana."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)
        self.platform_services.apply_blur_behind(self)


def create_app(argv: list[str] | None = None) -> tuple[QApplication, WelcomeWindow]:
    """Crea e inicializa la aplicación Qt y su ventana."""
    if argv is None:
        argv = sys.argv

    # Configuración de DPI antes de instanciar QApplication
    platform_services = get_platform_services()
    platform_services.set_dpi_awareness()

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    apply_dark_theme(app)

    settings = AppSettings.load()
    session_manager = SessionManager()
    window = WelcomeWindow(session_manager, settings)

    return app, window


def main() -> int:
    """Función principal de inicio de la aplicación."""
    setup_logging(debug=True)
    logger.info("Iniciando %s versión %s...", APP_NAME, APP_VERSION)

    # Permitir verificación rápida sin abrir ventana si se pasa --check o --version
    if "--check" in sys.argv:
        print(f"{APP_NAME} {APP_VERSION} [OK]")
        return 0

    app, window = create_app()
    window.show()
    return app.exec()
