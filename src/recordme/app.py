"""Punto de entrada de la aplicación RecordMe, inicialización de Qt y servicios."""

import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
)

from recordme.config.settings import AppSettings
from recordme.constants import APP_DISPLAY_NAME, APP_NAME, APP_VERSION
from recordme.core.recording_controller import RecordingController
from recordme.core.session import SessionManager
from recordme.platform_services.factory import get_platform_services
from recordme.ui.camera_preview import CameraPreviewWidget
from recordme.ui.region_selector import RegionSelectorOverlay
from recordme.ui.toolbar import FloatingToolbar
from recordme.utils.geometry import Rect
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


class RecordMeApp:
    """Coordinador principal de la interfaz y componentes de RecordMe."""

    def __init__(self, session_manager: SessionManager, settings: AppSettings) -> None:
        self.session_manager = session_manager
        self.settings = settings
        self.platform_services = get_platform_services()

        self.controller = RecordingController(session_manager, settings)
        self.toolbar = FloatingToolbar(session_manager)
        self.selector_overlay: RegionSelectorOverlay | None = None
        self.camera_preview: CameraPreviewWidget | None = None

        self._connect_signals()
        self._position_toolbar()

    def _connect_signals(self) -> None:
        """Conecta las señales entre la barra flotante y el controlador de grabación."""
        self.toolbar.request_region_selection.connect(self._open_region_selector)
        self.toolbar.request_start_record.connect(self._start_recording)
        self.toolbar.request_pause_record.connect(self.controller.pause_recording)
        self.toolbar.request_resume_record.connect(self.controller.resume_recording)
        self.toolbar.request_stop_record.connect(self.controller.stop_recording)
        self.toolbar.mic_toggled.connect(self.controller.set_mic_muted)
        self.toolbar.camera_toggled.connect(self._on_camera_toggled)

        self.controller.recording_finished.connect(self._on_recording_finished)
        self.controller.recording_failed.connect(self._on_recording_failed)

    def _on_camera_toggled(self, enabled: bool) -> None:
        """Activa o desactiva la burbuja de cámara y su previsualización en vivo."""
        if enabled:
            success = self.controller.set_camera_enabled(True)
            if success and self.controller.camera_source:
                self.camera_preview = CameraPreviewWidget(
                    initial_layout=self.controller.camera_layout,
                    capture_region=self.controller.current_region,
                )
                self.camera_preview.layout_updated.connect(self.controller.update_camera_layout)
                self.controller.camera_source.add_on_frame_callback(self.camera_preview.update_frame)
                self.camera_preview.show()
                logger.info("Vista previa de cámara mostrada en pantalla.")
            else:
                self.toolbar.set_camera_enabled(False)
                QMessageBox.warning(
                    self.toolbar,
                    APP_NAME,
                    "No se pudo acceder a la cámara. Comprueba que esté conectada y no esté en uso por otra aplicación.",
                )
        else:
            self.controller.set_camera_enabled(False)
            if self.camera_preview:
                self.camera_preview.close()
                self.camera_preview = None
                logger.info("Vista previa de cámara cerrada.")

    def _position_toolbar(self) -> None:
        """Ubica la barra flotante centrada en la parte superior de la pantalla."""
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + (geom.width() - self.toolbar.width()) // 2
            y = geom.y() + 40
            self.toolbar.move(x, y)

    def _open_region_selector(self) -> None:
        """Abre el overlay para seleccionar el área de pantalla."""
        self.selector_overlay = RegionSelectorOverlay()
        self.selector_overlay.region_selected.connect(self._on_region_selected)
        self.selector_overlay.show()

    def _on_region_selected(self, region: Rect) -> None:
        """Aplica la región elegida a la barra y al controlador."""
        self.controller.set_region(region)
        self.toolbar.update_selected_region(region)
        if self.camera_preview:
            self.camera_preview.update_capture_region(region)
        if self.selector_overlay:
            self.selector_overlay = None

    def _start_recording(self) -> None:
        """Inicia el proceso de grabación."""
        success = self.controller.start_recording()
        if not success:
            QMessageBox.critical(
                self.toolbar,
                APP_NAME,
                "No se pudo iniciar la grabación. Consulta los registros de log para más detalles.",
            )

    def _on_recording_finished(self, output_path: Path) -> None:
        """Muestra aviso al finalizar con opción para abrir la carpeta contenedora."""
        msg_box = QMessageBox(self.toolbar)
        msg_box.setWindowTitle(APP_NAME)
        msg_box.setText(f"Grabación guardada con éxito:\n\n{output_path.name}")
        msg_box.setInformativeText(f"Ubicación: {output_path.parent}")
        open_folder_btn = msg_box.addButton("Abrir carpeta", QMessageBox.ButtonRole.ActionRole)
        msg_box.addButton("Aceptar", QMessageBox.ButtonRole.AcceptRole)
        msg_box.exec()

        if msg_box.clickedButton() == open_folder_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_path.parent)))

    def _on_recording_failed(self, error: str) -> None:
        """Muestra error en caso de fallo durante la grabación."""
        QMessageBox.critical(
            self.toolbar,
            APP_NAME,
            f"Ocurrió un error durante la grabación:\n{error}",
        )

    def show(self) -> None:
        """Muestra la barra flotante."""
        self.toolbar.show()


def create_app(argv: list[str] | None = None) -> tuple[QApplication, RecordMeApp]:
    """Crea e inicializa la aplicación Qt y su controlador principal."""
    if argv is None:
        argv = sys.argv

    platform_services = get_platform_services()
    platform_services.set_dpi_awareness()

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    apply_dark_theme(app)

    settings = AppSettings.load()
    session_manager = SessionManager()
    recordme_app = RecordMeApp(session_manager, settings)

    return app, recordme_app


def main() -> int:
    """Función principal de inicio de la aplicación."""
    setup_logging(debug=True)
    logger.info("Iniciando %s versión %s...", APP_NAME, APP_VERSION)

    if "--check" in sys.argv:
        print(f"{APP_NAME} {APP_VERSION} [OK]")
        return 0

    app, recordme_app = create_app()
    recordme_app.show()
    return app.exec()
