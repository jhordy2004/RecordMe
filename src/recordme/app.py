"""Punto de entrada de la aplicación RecordMe, inicialización de Qt y servicios."""

import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QUrl
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMessageBox,
)

from recordme.config.settings import AppSettings, TeleprompterSettings
from recordme.constants import APP_DISPLAY_NAME, APP_NAME, APP_VERSION
from recordme.core.events import SessionState
from recordme.core.recording_controller import RecordingController
from recordme.core.render_state import CensorRegion
from recordme.core.session import SessionManager
from recordme.platform_services.factory import get_platform_services
from recordme.platform_services.hotkeys import GlobalHotkeyService
from recordme.ui.camera_preview import CameraPreviewWidget
from recordme.ui.camera_settings_dialog import CameraSettingsDialog
from recordme.ui.censor_box import CensorBoxWidget
from recordme.ui.censor_selector import CensorAreaSelectorOverlay
from recordme.ui.countdown import CountdownOverlay
from recordme.ui.region_frame import RegionFrameWidget
from recordme.ui.region_selector import RegionSelectorOverlay
from recordme.ui.screen_zoom_overlay import ScreenZoomOverlay
from recordme.ui.teleprompter import TeleprompterWidget
from recordme.ui.teleprompter_editor import TeleprompterEditorDialog
from recordme.ui.toolbar import FloatingToolbar
from recordme.utils.geometry import Rect, get_primary_screen_physical_rect, to_logical_pixels
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
        self.region_frame: RegionFrameWidget | None = None
        self.camera_preview: CameraPreviewWidget | None = None
        self.teleprompter_widget: TeleprompterWidget | None = None
        self.teleprompter_editor: TeleprompterEditorDialog | None = None
        self.countdown_overlay: CountdownOverlay | None = None
        self.censor_boxes: dict[str, CensorBoxWidget] = {}
        self.censor_selector_overlay: CensorAreaSelectorOverlay | None = None
        self.screen_zoom_overlay = ScreenZoomOverlay()
        self._is_testing_teleprompter = False

        self._zoom_level: float = 1.0
        self._zoom_cx: float = 0.5
        self._zoom_cy: float = 0.5

        self.hotkey_service = GlobalHotkeyService(self.toolbar)

        self._connect_signals()
        self._position_toolbar()
        self.hotkey_service.start()

    def _connect_signals(self) -> None:
        """Conecta las señales entre la barra flotante y el controlador de grabación."""
        self.toolbar.request_region_selection.connect(self._open_region_selector)
        self.toolbar.request_start_record.connect(self._initiate_recording)
        self.toolbar.request_pause_record.connect(self._pause_recording)
        self.toolbar.request_resume_record.connect(self._resume_recording)
        self.toolbar.request_stop_record.connect(self._stop_recording)
        self.toolbar.mic_toggled.connect(self.controller.set_mic_enabled)
        self.toolbar.camera_toggled.connect(self._on_camera_toggled)
        self.toolbar.teleprompter_clicked.connect(self._open_teleprompter_editor)
        self.toolbar.censor_clicked.connect(self._open_censor_area_selector)
        self.toolbar.request_exit.connect(self._exit_app)

        # Atajos globales de zoom y desplazamiento
        self.hotkey_service.zoom_in.connect(self._zoom_in_step)
        self.hotkey_service.zoom_out.connect(self._zoom_out_step)
        self.hotkey_service.zoom_reset.connect(self._zoom_reset)
        self.hotkey_service.pan_up.connect(lambda: self._pan_step(0.0, -0.06))
        self.hotkey_service.pan_down.connect(lambda: self._pan_step(0.0, 0.06))
        self.hotkey_service.pan_left.connect(lambda: self._pan_step(-0.06, 0.0))
        self.hotkey_service.pan_right.connect(lambda: self._pan_step(0.06, 0.0))

        self.controller.recording_finished.connect(self._on_recording_finished)
        self.controller.recording_failed.connect(self._on_recording_failed)

    def _on_camera_toggled(self, enabled: bool) -> None:
        """Abre el panel de configuración de cámara antes de activarla o la desactiva."""
        if enabled:
            dialog = CameraSettingsDialog(current_settings=self.settings.camera, parent=self.toolbar)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.controller.apply_camera_settings(self.settings.camera)
                success = self.controller.set_camera_enabled(True)
                if success and self.controller.camera_source:
                    if self.camera_preview:
                        self.camera_preview.close()
                    self.camera_preview = CameraPreviewWidget(
                        initial_layout=self.controller.camera_layout,
                        capture_region=self.controller.current_region,
                    )
                    self.camera_preview.layout_updated.connect(self.controller.update_camera_layout)
                    self.controller.camera_source.add_on_frame_callback(self.camera_preview.update_frame)
                    self.camera_preview.show()
                    self.toolbar.set_camera_enabled(True)
                    logger.info("Vista previa de cámara mostrada en pantalla.")
                else:
                    self.toolbar.set_camera_enabled(False)
                    QMessageBox.warning(
                        self.toolbar,
                        APP_NAME,
                        "No se pudo acceder a la cámara. Comprueba que esté conectada y no esté en uso por otra aplicación.",
                    )
            else:
                self.toolbar.set_camera_enabled(False)
        else:
            self.controller.set_camera_enabled(False)
            if self.camera_preview:
                self.camera_preview.close()
                self.camera_preview = None
                logger.info("Vista previa de cámara cerrada.")

    def _position_toolbar(self, at_bottom: bool = False) -> None:
        """Ubica la barra flotante centrada en la parte superior o inferior de la pantalla."""
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + (geom.width() - self.toolbar.width()) // 2
            if at_bottom:
                y = geom.y() + geom.height() - self.toolbar.height() - 30
            else:
                y = geom.y() + 40
            self.toolbar.move(x, y)

    def _open_region_selector(self) -> None:
        """Abre el overlay para seleccionar el área de pantalla."""
        self.selector_overlay = RegionSelectorOverlay()
        self.selector_overlay.region_selected.connect(self._on_region_selected)
        self.selector_overlay.show()

    def _on_region_selected(self, region: Rect) -> None:
        """Aplica la región elegida a la barra, al controlador y al marco visual interactivo."""
        self.controller.set_region(region)
        self.toolbar.update_selected_region(region)
        if self.camera_preview:
            self.camera_preview.update_capture_region(region)
        if self.selector_overlay:
            self.selector_overlay = None

        screen = QApplication.primaryScreen()
        screen_rect = get_primary_screen_physical_rect()
        dpr = screen.devicePixelRatio() if screen else 1.0

        # Si es un área personalizada (menor que la pantalla completa), mostrar marco interactivo
        if region.width < screen_rect.width or region.height < screen_rect.height:
            if self.region_frame is None:
                self.region_frame = RegionFrameWidget()
                self.region_frame.region_changed.connect(self._on_frame_region_changed)
                self.region_frame.reset_fullscreen_requested.connect(self._reset_to_fullscreen)
            self.region_frame.set_physical_region(region, dpr)
            self.region_frame.show()
        else:
            if self.region_frame:
                self.region_frame.close()
                self.region_frame = None

    def _on_frame_region_changed(self, region: Rect) -> None:
        """Sincroniza la región modificada mediante los bordes del marco interactivo."""
        self.controller.set_region(region)
        self.toolbar.update_selected_region(region)
        if self.camera_preview:
            self.camera_preview.update_capture_region(region)

    def _reset_to_fullscreen(self) -> None:
        """Restaura la región de grabación a la pantalla completa."""
        screen_rect = get_primary_screen_physical_rect()
        self._on_region_selected(screen_rect)

    def _initiate_recording(self) -> None:
        """Inicia la cuenta regresiva antes de comenzar la grabación."""
        if self.session_manager.state not in (SessionState.IDLE, SessionState.CONFIGURING, SessionState.DONE):
            return

        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0

        # Si el área es pantalla completa o región personalizada
        screen_phys = get_primary_screen_physical_rect()
        is_fullscreen = (
            self.controller.current_region.width >= screen_phys.width
            and self.controller.current_region.height >= screen_phys.height
        )

        if is_fullscreen:
            target_rect = screen.geometry() if screen else None
        else:
            log_x = to_logical_pixels(self.controller.current_region.x, dpr)
            log_y = to_logical_pixels(self.controller.current_region.y, dpr)
            log_w = to_logical_pixels(self.controller.current_region.width, dpr)
            log_h = to_logical_pixels(self.controller.current_region.height, dpr)
            target_rect = QRect(log_x, log_y, log_w, log_h)

        self.session_manager.transition_to(SessionState.COUNTDOWN)
        self.countdown_overlay = CountdownOverlay(target_rect=target_rect, seconds=3)
        self.countdown_overlay.finished.connect(self._on_countdown_finished)
        self.countdown_overlay.canceled.connect(self._on_countdown_canceled)
        self.countdown_overlay.start()

    def _on_countdown_finished(self) -> None:
        """Comienza la grabación efectiva tras concluir la cuenta atrás."""
        self.countdown_overlay = None
        self._start_recording()

    def _on_countdown_canceled(self) -> None:
        """Cancela la cuenta regresiva y regresa a IDLE."""
        self.countdown_overlay = None
        self.session_manager.transition_to(SessionState.IDLE)

    def _start_recording(self) -> None:
        """Inicia el proceso de grabación y arranca el scroll del teleprompter si está activo."""
        success = self.controller.start_recording()
        if success:
            if self.region_frame:
                self.region_frame.set_recording_state(True)
            if self.teleprompter_widget and self.teleprompter_widget.isVisible():
                self.teleprompter_widget.start_scrolling()
        else:
            QMessageBox.critical(
                self.toolbar,
                APP_NAME,
                "No se pudo iniciar la grabación. Consulta los registros de log para más detalles.",
            )

    def _zoom_in_step(self) -> None:
        """Aumenta el zoom un 10% (Ctrl++). Centra en el cursor si parte del 100%."""
        if self._zoom_level <= 1.01:
            cursor_pos = QCursor.pos()
            screen = QApplication.primaryScreen()
            dpr = screen.devicePixelRatio() if screen else 1.0
            phys_x = cursor_pos.x() * dpr
            phys_y = cursor_pos.y() * dpr
            reg = self.controller.current_region
            if reg.contains(int(phys_x), int(phys_y)):
                self._zoom_cx = max(0.05, min(0.95, (phys_x - reg.x) / max(1, reg.width)))
                self._zoom_cy = max(0.05, min(0.95, (phys_y - reg.y) / max(1, reg.height)))
            else:
                self._zoom_cx = 0.5
                self._zoom_cy = 0.5

        self._zoom_level = min(3.0, round(self._zoom_level + 0.10, 2))
        self._apply_zoom()
        logger.info("Zoom aumentado a %.0f%% (centro: %.2f, %.2f)", self._zoom_level * 100, self._zoom_cx, self._zoom_cy)

    def _zoom_out_step(self) -> None:
        """Reduce el zoom un 10% (Ctrl+-)."""
        self._zoom_level = max(1.0, round(self._zoom_level - 0.10, 2))
        if self._zoom_level <= 1.01:
            self._zoom_cx = 0.5
            self._zoom_cy = 0.5
        self._apply_zoom()
        logger.info("Zoom reducido a %.0f%% (centro: %.2f, %.2f)", self._zoom_level * 100, self._zoom_cx, self._zoom_cy)

    def _zoom_reset(self) -> None:
        """Restablece el zoom a 100% (Ctrl+0)."""
        self._zoom_level = 1.0
        self._zoom_cx = 0.5
        self._zoom_cy = 0.5
        self._apply_zoom()
        logger.info("Zoom restablecido al 100%%.")

    def _pan_step(self, dx: float, dy: float) -> None:
        """Desplaza el encuadre de zoom con las flechas del teclado (Ctrl+Flechas)."""
        if self._zoom_level <= 1.01:
            return
        self._zoom_cx = max(0.0, min(1.0, round(self._zoom_cx + dx, 3)))
        self._zoom_cy = max(0.0, min(1.0, round(self._zoom_cy + dy, 3)))
        self._apply_zoom()
        logger.info("Paneo de zoom desplazado: centro en (%.2f, %.2f)", self._zoom_cx, self._zoom_cy)

    def _apply_zoom(self) -> None:
        """Aplica el nivel de zoom y centro al controlador, a la barra y al overlay de pantalla completa."""
        if self._zoom_level <= 1.01:
            self._zoom_cx = 0.5
            self._zoom_cy = 0.5
        self.controller.set_zoom(self._zoom_level, self._zoom_cx, self._zoom_cy)
        self.toolbar.update_zoom_display(self._zoom_level)
        self.screen_zoom_overlay.set_zoom(self._zoom_level, self._zoom_cx, self._zoom_cy)

    def _open_censor_area_selector(self) -> None:
        """Abre el overlay para que el usuario trace interactivamente el área a censurar."""
        self.censor_selector_overlay = CensorAreaSelectorOverlay()
        self.censor_selector_overlay.area_selected.connect(self._on_censor_area_drawn)
        self.censor_selector_overlay.show()

    def _on_censor_area_drawn(self, rect: QRect) -> None:
        """Crea un nuevo recuadro de censura en el área exacta seleccionada por el usuario."""
        self.censor_selector_overlay = None
        self._create_censor_box(rect=rect, mode="blur")

    def _create_censor_box(self, rect: QRect, mode: str = "blur") -> CensorBoxWidget:
        """Crea y registra una caja de censura flotante."""
        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0

        box_id = str(uuid.uuid4())[:8]
        box = CensorBoxWidget(box_id=box_id, initial_rect=rect, mode=mode, dpr=dpr)
        box.geometry_changed.connect(self._on_censor_box_changed)
        box.box_closed.connect(self._on_censor_box_closed)
        box.duplicate_requested.connect(self._on_censor_box_duplicate)

        self.censor_boxes[box_id] = box
        self._sync_censor_regions()
        box.show()
        logger.info("Caja de censura creada: %s en %s", box_id, rect)
        return box

    def _on_censor_box_duplicate(self, box_id: str) -> None:
        """Duplica una caja de censura existente con un desplazamiento de +25px."""
        orig_box = self.censor_boxes.get(box_id)
        if not orig_box:
            return
        orig_geom = orig_box.geometry()
        dup_rect = QRect(orig_geom.x() + 25, orig_geom.y() + 25, orig_geom.width(), orig_geom.height())
        self._create_censor_box(rect=dup_rect, mode=orig_box.mode)

    def _on_censor_box_changed(self, box_id: str, phys_rect: Rect, mode: str) -> None:
        """Actualiza las regiones de censura activas al mover o redimensionar una caja."""
        self._sync_censor_regions()

    def _on_censor_box_closed(self, box_id: str) -> None:
        """Elimina la caja de censura y actualiza el compositor."""
        self.censor_boxes.pop(box_id, None)
        self._sync_censor_regions()

    def _sync_censor_regions(self) -> None:
        """Construye y envía la lista actualizada de CensorRegion al controlador."""
        regions = [
            CensorRegion(
                id=box.box_id,
                rect=box.get_physical_region(),
                mode=box.mode,
                active=True,
            )
            for box in self.censor_boxes.values()
        ]
        self.controller.set_censor_regions(regions)

    def _pause_recording(self) -> None:
        """Pausa la grabación y el teleprompter simultáneamente."""
        self.controller.pause_recording()
        if self.teleprompter_widget:
            self.teleprompter_widget.pause_scrolling()

    def _resume_recording(self) -> None:
        """Reanuda la grabación y el teleprompter simultáneamente."""
        self.controller.resume_recording()
        if self.teleprompter_widget:
            self.teleprompter_widget.resume_scrolling()

    def _stop_recording(self) -> None:
        """Detiene la grabación solicitando interactivamente al usuario la ruta y nombre para guardar."""
        now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_folder = Path(self.settings.output.folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        default_file = output_folder / f"Grabacion_{now_str}.mp4"

        # Diálogo nativo modal y sobrepuesto sobre la barra flotante
        dialog = QFileDialog(self.toolbar, "Guardar grabación", str(default_file), "Video MP4 (*.mp4)")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDefaultSuffix("mp4")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dialog.raise_()
        dialog.activateWindow()

        target_path: Path | None = None
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            files = dialog.selectedFiles()
            if files:
                target_path = Path(files[0])

        if target_path is not None:
            self.controller.stop_recording(target_output_file=target_path)
        else:
            # Usuario canceló el guardado: descartar la grabación limpia
            self.controller.cancel_recording()

        if self.region_frame:
            self.region_frame.close()
            self.region_frame = None

        # Cerrar recuadros de censura y limpiar estado
        for box in list(self.censor_boxes.values()):
            box.close()
        self.censor_boxes.clear()
        self.controller.set_censor_regions([])

        # Reset zoom al terminar
        self._zoom_level = 1.0
        self._zoom_cx = 0.5
        self._zoom_cy = 0.5
        self._apply_zoom()

        # Restablecer el área a pantalla completa para que la selección desaparezca
        screen_rect = get_primary_screen_physical_rect()
        self.controller.set_region(screen_rect)
        self.toolbar.update_selected_region(screen_rect)
        if self.camera_preview:
            self.camera_preview.update_capture_region(screen_rect)
        if self.teleprompter_widget:
            self.teleprompter_widget.pause_scrolling()

    def _open_teleprompter_editor(self) -> None:
        """Abre el editor completo del teleprompter de forma interactiva y no bloqueante."""
        if self.teleprompter_editor is None:
            self.teleprompter_editor = TeleprompterEditorDialog(
                current_text=self.settings.teleprompter.last_script,
                settings=self.settings.teleprompter,
            )
            self.teleprompter_editor.settings_applied.connect(self._on_teleprompter_applied)
            self.teleprompter_editor.test_requested.connect(self._on_teleprompter_test)
            self.teleprompter_editor.stop_test_requested.connect(self._on_teleprompter_stop_test)
        else:
            self.teleprompter_editor.update_from_settings(self.settings.teleprompter)

        self.teleprompter_editor.show()
        self.teleprompter_editor.raise_()
        self.teleprompter_editor.activateWindow()

    def _on_teleprompter_applied(self, text: str, settings: TeleprompterSettings) -> None:
        """Aplica el texto y ajustes al widget flotante del teleprompter y guarda configuración."""
        self.settings.teleprompter = settings
        self.settings.save()

        if self.teleprompter_widget is None:
            self.teleprompter_widget = TeleprompterWidget(text=text, settings=settings)
            self.teleprompter_widget.closed.connect(self._on_teleprompter_closed)
        else:
            self.teleprompter_widget.update_settings(settings)
            self.teleprompter_widget.set_script(text)

        self.teleprompter_widget.show()
        # Reposicionar la barra flotante abajo para que no colisione con el teleprompter arriba
        self._position_toolbar(at_bottom=True)
        self.toolbar.show()
        logger.info("Teleprompter visible y barra reposicionada en la parte inferior.")

    def _on_teleprompter_test(self, text: str, settings: TeleprompterSettings) -> None:
        """Lanza una prueba interactiva del teleprompter con controles habilitados."""
        self._is_testing_teleprompter = True
        if self.teleprompter_widget is None:
            self.teleprompter_widget = TeleprompterWidget(text=text, settings=settings)
            self.teleprompter_widget.closed.connect(self._on_teleprompter_closed)
        else:
            self.teleprompter_widget.update_settings(settings)
            self.teleprompter_widget.set_script(text)

        self.teleprompter_widget.show()
        self.teleprompter_widget.reset_scroll()
        self.teleprompter_widget.start_scrolling()

    def _on_teleprompter_stop_test(self) -> None:
        """Detiene la prueba en vivo del teleprompter."""
        if self.teleprompter_widget:
            self.teleprompter_widget.pause_scrolling()

    def _on_teleprompter_closed(self) -> None:
        """Maneja el evento cuando el usuario cierra el teleprompter."""
        logger.info("Teleprompter cerrado.")
        if self._is_testing_teleprompter:
            self._is_testing_teleprompter = False
            if self.teleprompter_editor:
                self.teleprompter_editor.show()
                self.teleprompter_editor.raise_()
                self.teleprompter_editor.activateWindow()
        else:
            # Si el teleprompter no está en prueba y se cierra, restaurar la barra arriba
            self._position_toolbar(at_bottom=False)

    def _exit_app(self) -> None:
        """Cierra inmediatamente la aplicación sin guardar nada si está grabando."""
        logger.info("Cierre de aplicación solicitado.")
        if self.session_manager.state in (SessionState.RECORDING, SessionState.PAUSED, SessionState.COUNTDOWN):
            self.controller.cancel_recording()
        self.hotkey_service.stop()
        for box in list(self.censor_boxes.values()):
            box.close()
        self.censor_boxes.clear()
        if self.camera_preview:
            self.camera_preview.close()
        if self.teleprompter_widget:
            self.teleprompter_widget.close()
        if self.teleprompter_editor:
            self.teleprompter_editor.close()
        if self.region_frame:
            self.region_frame.close()
        if self.selector_overlay:
            self.selector_overlay.close()
        if self.censor_selector_overlay:
            self.censor_selector_overlay.close()
        self.screen_zoom_overlay.set_zoom(1.0)
        self.screen_zoom_overlay.close()
        self.toolbar.close()
        QApplication.quit()

    def _on_recording_finished(self, output_path: Path) -> None:
        """Muestra aviso al finalizar sobrepuesto en pantalla con opción para abrir la carpeta contenedora."""
        msg_box = QMessageBox(self.toolbar)
        msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        msg_box.setWindowTitle(APP_NAME)
        msg_box.setText(f"Grabación guardada con éxito:\n\n{output_path.name}")
        msg_box.setInformativeText(f"Ubicación: {output_path.parent}")
        open_folder_btn = msg_box.addButton("Abrir carpeta", QMessageBox.ButtonRole.ActionRole)
        msg_box.addButton("Aceptar", QMessageBox.ButtonRole.AcceptRole)
        msg_box.raise_()
        msg_box.activateWindow()
        msg_box.exec()

        if msg_box.clickedButton() == open_folder_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_path.parent)))

        if self.session_manager.state == SessionState.DONE:
            self.session_manager.transition_to(SessionState.IDLE)

    def _on_recording_failed(self, error: str) -> None:
        """Muestra error en caso de fallo durante la grabación."""
        QMessageBox.critical(
            self.toolbar,
            APP_NAME,
            f"Ocurrió un error durante la grabación:\n{error}",
        )
        if self.session_manager.state == SessionState.ERROR:
            self.session_manager.transition_to(SessionState.IDLE)

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
    app.setQuitOnLastWindowClosed(False)
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
