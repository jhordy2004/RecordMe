"""Punto de entrada de la aplicación RecordMe, inicialización de Qt y servicios."""

import logging
import shutil
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRect, Qt
from PySide6.QtGui import QColor, QCursor, QPalette
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QFileDialog,
    QMessageBox,
    QPushButton,
)

from recordme.config.paths import get_default_recordings_dir
from recordme.config.settings import AppSettings, AudioSettings, TeleprompterSettings
from recordme.constants import APP_DISPLAY_NAME, APP_NAME, APP_VERSION
from recordme.core.events import SessionState
from recordme.core.recording_controller import RecordingController
from recordme.core.render_state import CensorRegion
from recordme.core.session import SessionManager
from recordme.platform_services.factory import get_platform_services
from recordme.platform_services.hotkeys import GlobalHotkeyService
from recordme.resources import get_app_icon, setup_app_user_model_id
from recordme.ui.audio_settings_dialog import AudioSettingsDialog
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
from recordme.utils.i18n import init_language, tr
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
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(20, 20, 20))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(250, 250, 250))
    palette.setColor(QPalette.ColorRole.Text, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    app.setPalette(palette)
    app.setStyleSheet(
        """
        QToolTip {
            background-color: #1A1A1A;
            color: #FFFFFF;
            border: 1px solid #444444;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 600;
        }
        """
    )


class ButtonCursorEventFilter(QObject):
    """Garantiza que todos los botones de la interfaz muestren el cursor pointer."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in (QEvent.Type.Show, QEvent.Type.Polish):
            if isinstance(watched, (QPushButton, QAbstractButton)):
                watched.setCursor(Qt.CursorShape.PointingHandCursor)
        return super().eventFilter(watched, event)


class RecordMeApp:
    """Coordinador principal de la interfaz y componentes de RecordMe."""

    def __init__(self, session_manager: SessionManager, settings: AppSettings) -> None:
        self.session_manager = session_manager
        self.settings = settings
        forced_lang = (
            self.settings.language
            if self.settings.language in ("es", "zh", "en") and self.settings.language != "auto"
            else None
        )
        init_language(forced_lang)
        self.platform_services = get_platform_services()

        self.controller = RecordingController(session_manager, settings)
        self.toolbar = FloatingToolbar(session_manager)
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.toolbar.setWindowIcon(app_icon)
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
        self._camera_dialog_open = False

        self._zoom_level: float = 1.0
        self._zoom_cx: float = 0.5
        self._zoom_cy: float = 0.5

        self.hotkey_service = GlobalHotkeyService(self.toolbar)

        self._connect_signals()
        self._position_toolbar()
        self.hotkey_service.start()

        if sys.platform == "darwin":
            self._verify_macos_permissions()

    def _verify_macos_permissions(self) -> None:
        """Comprueba permisos de macOS y orienta al usuario si faltan accesos de pantalla o accesibilidad."""
        try:
            perms = self.platform_services.request_permissions()
            missing = []
            if not perms.get("screen_capture", True):
                missing.append("Grabación de pantalla (Ajustes del Sistema > Privacidad y Seguridad > Grabación de Pantalla)")
            if not perms.get("accessibility", True):
                missing.append("Accesibilidad para atajos globales (Ajustes del Sistema > Privacidad y Seguridad > Accesibilidad)")

            if missing:
                msg = (
                    "Para que RecordMe funcione al 100% en macOS se requieren los siguientes permisos:\n\n• "
                    + "\n• ".join(missing)
                    + "\n\nPor favor, otorga los accesos necesarios para habilitar la captura con ScreenCaptureKit y los atajos de teclado."
                )
                logger.warning(msg)
                QMessageBox.information(
                    self.toolbar,
                    "Permisos de macOS — RecordMe",
                    msg,
                )
        except Exception as e:
            logger.debug("Error comprobando permisos de macOS: %s", e)

    def _connect_signals(self) -> None:
        """Conecta las señales entre la barra flotante y el controlador de grabación."""
        self.toolbar.request_region_selection.connect(self._open_region_selector)
        self.toolbar.request_start_record.connect(self._initiate_recording)
        self.toolbar.request_pause_record.connect(self._pause_recording)
        self.toolbar.request_resume_record.connect(self._resume_recording)
        self.toolbar.request_stop_record.connect(self._stop_recording)
        self.toolbar.mic_settings_requested.connect(self._open_audio_settings_dialog)
        self.toolbar.mic_toggled.connect(self.controller.set_mic_enabled)
        self.toolbar.camera_toggled.connect(self._on_camera_toggled)
        self.toolbar.teleprompter_clicked.connect(self._open_teleprompter_editor)
        self.toolbar.censor_clicked.connect(self._open_censor_area_selector)
        self.toolbar.request_exit.connect(self._exit_app)
        self.toolbar.escape_pressed.connect(self._on_escape_pressed)

        # Atajos globales de zoom y desplazamiento
        self.hotkey_service.zoom_in.connect(self._zoom_in_step)
        self.hotkey_service.zoom_out.connect(self._zoom_out_step)
        self.hotkey_service.zoom_reset.connect(self._zoom_reset)
        self.hotkey_service.pan_up.connect(lambda: self._pan_step(0.0, -0.10))
        self.hotkey_service.pan_down.connect(lambda: self._pan_step(0.0, 0.10))
        self.hotkey_service.pan_left.connect(lambda: self._pan_step(-0.10, 0.0))
        self.hotkey_service.pan_right.connect(lambda: self._pan_step(0.10, 0.0))

        # Atajos globales directos (L: Área, R: Grabar/Detener, P: Pausa, M: Mic, C: Cámara, T: Teleprompter, X: Censura, Q: Salir)
        self.hotkey_service.trigger_area.connect(self._open_region_selector)
        self.hotkey_service.trigger_record.connect(self._on_hotkey_record)
        self.hotkey_service.trigger_pause.connect(self._on_hotkey_pause)
        self.hotkey_service.trigger_mic.connect(self.toolbar.toggle_mic_mute)
        self.hotkey_service.trigger_camera.connect(self.toolbar._toggle_camera)
        self.hotkey_service.trigger_teleprompter.connect(self._toggle_teleprompter)
        self.hotkey_service.trigger_censor.connect(self._open_censor_area_selector)
        self.hotkey_service.trigger_exit.connect(self._exit_app)
        self.hotkey_service.trigger_escape.connect(self._on_escape_pressed)

        self.controller.recording_finished.connect(self._on_recording_finished)
        self.controller.recording_failed.connect(self._on_recording_failed)

    def _on_hotkey_record(self) -> None:
        """Maneja el atajo de teclado para iniciar o detener grabación sin disparar nuevas grabaciones."""
        if self.session_manager.state in (SessionState.RECORDING, SessionState.COUNTDOWN, SessionState.PAUSED):
            logger.info("Atajo R: Deteniendo grabación actual.")
            self._stop_recording()
        elif self.session_manager.state == SessionState.IDLE:
            logger.info("Atajo R: Iniciando grabación.")
            self._initiate_recording()
        else:
            logger.debug("Atajo R ignorado en estado: %s", self.session_manager.state.name)

    def _on_hotkey_pause(self) -> None:
        """Maneja el atajo de teclado para alternar pausa/reanudación."""
        if self.session_manager.state in (SessionState.RECORDING, SessionState.COUNTDOWN):
            logger.info("Atajo P: Pausando grabación.")
            self._pause_recording()
        elif self.session_manager.state == SessionState.PAUSED:
            logger.info("Atajo P: Reanudando grabación.")
            self._resume_recording()
        else:
            logger.debug("Atajo P ignorado en estado: %s", self.session_manager.state.name)

    def _on_camera_toggled(self, enabled: bool) -> None:
        """Abre el panel de configuración de cámara si está inactiva, o la apaga y quita su miniatura."""
        if self._camera_dialog_open:
            logger.info("El diálogo de cámara ya se encuentra abierto. Ignorando atajo C.")
            return

        if self.camera_preview is not None or not enabled:
            # Desactivar y remover la miniatura
            if self.controller.camera_source and self.camera_preview:
                try:
                    self.controller.camera_source.remove_on_frame_callback(self.camera_preview.update_frame)
                except Exception:
                    pass
            if self.camera_preview:
                self.camera_preview.hide()
                self.camera_preview.close()
                self.camera_preview.deleteLater()
                self.camera_preview = None
            self.controller.set_camera_enabled(False)
            self.toolbar.set_camera_enabled(False)
            logger.info("Miniatura de cámara desactivada y removida de pantalla.")
            return

        # Si está inactiva, abrir el diálogo de configuración evitando ventanas duplicadas
        self._camera_dialog_open = True
        try:
            dialog = CameraSettingsDialog(
                current_settings=self.settings.camera,
                camera_source=self.controller.camera_source,
                parent=self.toolbar,
            )
            self.platform_services.exclude_window_from_capture(dialog)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.controller.apply_camera_settings(self.settings.camera)
                success = self.controller.set_camera_enabled(True)
                if success and self.controller.camera_source:
                    if self.camera_preview:
                        self.camera_preview.hide()
                        self.camera_preview.close()
                        self.camera_preview = None
                    self.camera_preview = CameraPreviewWidget(
                        initial_layout=self.controller.camera_layout,
                        capture_region=self.controller.current_region,
                    )
                    self.camera_preview.layout_updated.connect(self.controller.update_camera_layout)
                    self.camera_preview.close_requested.connect(lambda: self._on_camera_toggled(False))
                    self.controller.camera_source.add_on_frame_callback(self.camera_preview.update_frame)
                    self.camera_preview.show()
                    self.toolbar.set_camera_enabled(True)
                    logger.info("Vista previa de cámara mostrada en pantalla.")
                else:
                    self.toolbar.set_camera_enabled(False)
                    QMessageBox.warning(
                        self.toolbar,
                        APP_NAME,
                        tr("recording_error_msg", err="No se pudo acceder a la cámara."),
                    )
            else:
                self.toolbar.set_camera_enabled(False)
        finally:
            self._camera_dialog_open = False

    def _open_audio_settings_dialog(self) -> None:
        """Abre el panel modal de configuración de audio (micrófono, loopback del sistema y supresión de ruido)."""
        dialog = AudioSettingsDialog(
            current_settings=self.settings.audio,
            parent=self.toolbar,
        )
        self.platform_services.exclude_window_from_capture(dialog)
        dialog.settings_applied.connect(self._on_audio_settings_applied)
        dialog.exec()

    def _on_audio_settings_applied(self, new_settings: AudioSettings) -> None:
        """Aplica y persiste la configuración de audio seleccionada."""
        self.settings.audio = new_settings
        self.controller.apply_audio_settings(new_settings)
        self.settings.save()
        self.toolbar.set_mic_enabled(new_settings.mic_enabled)
        logger.info(
            "Configuración de audio guardada y aplicada: modo=%s, supresión_ruido=%s",
            new_settings.mode,
            new_settings.noise_reduction,
        )

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
        if self.session_manager.state in (SessionState.RECORDING, SessionState.COUNTDOWN, SessionState.PAUSED):
            logger.debug("Selección de área ignorada en estado: %s", self.session_manager.state.name)
            return

        # Si ya existe un overlay visible, traerlo al frente
        if self.selector_overlay is not None and self.selector_overlay.isVisible():
            self.selector_overlay.raise_()
            self.selector_overlay.activateWindow()
            return

        # Limpiar overlay anterior si quedó oculto o cerrado
        if self.selector_overlay is not None:
            try:
                self.selector_overlay.close()
                self.selector_overlay.deleteLater()
            except Exception:
                pass
            self.selector_overlay = None

        self.selector_overlay = RegionSelectorOverlay()
        self.selector_overlay.region_selected.connect(self._on_region_selected)
        self.selector_overlay.selection_canceled.connect(self._on_region_selector_canceled)
        self.selector_overlay.destroyed.connect(self._on_region_selector_destroyed)
        self.selector_overlay.show()
        self.selector_overlay.raise_()
        self.selector_overlay.activateWindow()

    def _on_region_selector_canceled(self) -> None:
        """Limpia el selector de área si el usuario canceló con Esc o clic derecho."""
        if self.selector_overlay is not None:
            try:
                self.selector_overlay.close()
                self.selector_overlay.deleteLater()
            except Exception:
                pass
            self.selector_overlay = None

    def _on_region_selector_destroyed(self) -> None:
        """Sincroniza el selector de área cuando Qt destruye el widget."""
        self.selector_overlay = None

    def _on_region_selected(self, region: Rect) -> None:
        """Aplica la región elegida a la barra, al controlador y al marco visual interactivo."""
        self.controller.set_region(region)
        self.toolbar.update_selected_region(region)
        if self.camera_preview:
            self.camera_preview.update_capture_region(region)
        if self.selector_overlay is not None:
            try:
                self.selector_overlay.close()
                self.selector_overlay.deleteLater()
            except Exception:
                pass
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

            # En Linux (X11/Wayland), aplicar estrategia de colocación fuera del área seleccionada
            if hasattr(self.platform_services, "reposition_outside_region"):
                self.platform_services.reposition_outside_region(self.toolbar, region, screen_rect)
                if self.teleprompter and self.teleprompter.isVisible():
                    self.platform_services.reposition_outside_region(self.teleprompter, region, screen_rect)
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

    def _on_escape_pressed(self) -> None:
        """Maneja la pulsación de Esc para cancelar selectores activos o eliminar el área seleccionada."""
        if self.selector_overlay is not None and self.selector_overlay.isVisible():
            self._on_region_selector_canceled()
            return
        if self.censor_selector_overlay is not None and self.censor_selector_overlay.isVisible():
            self._on_censor_area_canceled()
            return
        if (
            self.region_frame is not None
            and self.region_frame.isVisible()
            and self.session_manager.state == SessionState.IDLE
        ):
            logger.info("Esc detectado: eliminando selección de área y restableciendo a pantalla completa.")
            self._reset_to_fullscreen()
            return

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
        # Pre-calentar el pipeline en segundo plano durante la cuenta atrás para que al llegar a 0 la grabación sea instantánea
        prewarmed = self.controller.start_recording(standby_countdown=True)
        if not prewarmed:
            logger.warning("Fallo al pre-calentar el pipeline de grabación. Regresando a IDLE.")
            self.session_manager.transition_to(SessionState.IDLE)
            return
        self.countdown_overlay = CountdownOverlay(target_rect=target_rect, seconds=3)
        self.countdown_overlay.finished.connect(self._on_countdown_finished)
        self.countdown_overlay.canceled.connect(self._on_countdown_canceled)
        self.countdown_overlay.start()

    def _on_countdown_finished(self) -> None:
        """Comienza la grabación efectiva de forma instantánea (0 ms de espera tras la cuenta atrás)."""
        self.countdown_overlay = None
        self._start_recording()

    def _on_countdown_canceled(self) -> None:
        """Cancela la cuenta regresiva, aborta el pipeline pre-calentado y regresa a IDLE."""
        self.countdown_overlay = None
        self.controller.cancel_recording()

    def _start_recording(self) -> None:
        """Activa la grabación inmediatamente."""
        if self.session_manager.state == SessionState.COUNTDOWN:
            success = self.controller.activate_recording()
        else:
            success = self.controller.start_recording()
        if success:
            if self.region_frame:
                self.region_frame.set_recording_state(True)
        else:
            QMessageBox.critical(
                self.toolbar,
                APP_NAME,
                tr("recording_error_msg", err="No se pudo iniciar la grabación."),
            )

    def _zoom_in_step(self) -> None:
        """Aumenta el zoom un 10% (Alt++). Centra en el cursor si parte del 100%."""
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
        """Reduce el zoom un 10% (Alt+-)."""
        self._zoom_level = max(1.0, round(self._zoom_level - 0.10, 2))
        if self._zoom_level <= 1.01:
            self._zoom_cx = 0.5
            self._zoom_cy = 0.5
        self._apply_zoom()
        logger.info("Zoom reducido a %.0f%% (centro: %.2f, %.2f)", self._zoom_level * 100, self._zoom_cx, self._zoom_cy)

    def _zoom_reset(self) -> None:
        """Restablece el zoom a 100% (Alt+0)."""
        self._zoom_level = 1.0
        self._zoom_cx = 0.5
        self._zoom_cy = 0.5
        self._apply_zoom()
        logger.info("Zoom restablecido al 100%%.")

    def _pan_step(self, dx: float, dy: float) -> None:
        """Desplaza el encuadre de zoom con las flechas del teclado (Alt+Flechas o Flechas directas)."""
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
        self.hotkey_service.set_zoom_active(self._zoom_level > 1.01)

    def _open_censor_area_selector(self) -> None:
        """Abre el overlay para que el usuario trace interactivamente el área a censurar."""
        if self.censor_selector_overlay is not None and self.censor_selector_overlay.isVisible():
            self.censor_selector_overlay.raise_()
            self.censor_selector_overlay.activateWindow()
            return

        if self.censor_selector_overlay is not None:
            try:
                self.censor_selector_overlay.close()
                self.censor_selector_overlay.deleteLater()
            except Exception:
                pass
            self.censor_selector_overlay = None

        self.censor_selector_overlay = CensorAreaSelectorOverlay()
        self.censor_selector_overlay.area_selected.connect(self._on_censor_area_drawn)
        self.censor_selector_overlay.selection_canceled.connect(self._on_censor_area_canceled)
        self.censor_selector_overlay.destroyed.connect(self._on_censor_selector_destroyed)
        self.censor_selector_overlay.show()
        self.censor_selector_overlay.raise_()
        self.censor_selector_overlay.activateWindow()

    def _on_censor_area_canceled(self) -> None:
        """Limpia el selector de censura si el usuario canceló con Esc o clic derecho."""
        if self.censor_selector_overlay is not None:
            try:
                self.censor_selector_overlay.close()
                self.censor_selector_overlay.deleteLater()
            except Exception:
                pass
            self.censor_selector_overlay = None

    def _on_censor_selector_destroyed(self) -> None:
        """Sincroniza el selector de censura cuando Qt destruye el widget."""
        self.censor_selector_overlay = None

    def _on_censor_area_drawn(self, rect: QRect) -> None:
        """Crea un nuevo recuadro de censura en el área exacta seleccionada por el usuario."""
        if self.censor_selector_overlay is not None:
            try:
                self.censor_selector_overlay.close()
                self.censor_selector_overlay.deleteLater()
            except Exception:
                pass
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
        """Detiene la grabación de inmediato o cancela la cuenta regresiva si aún no empezó."""
        if self.countdown_overlay:
            self._on_countdown_canceled()
            return

        if self.session_manager.state in (SessionState.RECORDING, SessionState.PAUSED):
            self.controller.stop_recording()

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
            try:
                self.camera_preview.update_capture_region(screen_rect)
            except Exception as e:
                logger.debug("Aviso actualizando región en camera preview: %s", e)
        if self.teleprompter_widget:
            try:
                self.teleprompter_widget.pause_scrolling()
            except Exception as e:
                logger.debug("Aviso pausando teleprompter al detener: %s", e)

    def _toggle_teleprompter(self) -> None:
        """Alterna la visibilidad del teleprompter si ya fue configurado, o abre el editor si aún no existe."""
        if self.teleprompter_widget is not None:
            if self.teleprompter_widget.isVisible():
                self.teleprompter_widget.hide()
                logger.info("Teleprompter ocultado vía atajo Alt+T.")
            else:
                self.teleprompter_widget.show()
                self.teleprompter_widget.raise_()
                logger.info("Teleprompter restaurado vía atajo Alt+T.")
            return

        self._open_teleprompter_editor()

    def _open_teleprompter_editor(self) -> None:
        """Abre el editor completo del teleprompter de forma interactiva y no bloqueante."""
        if self.teleprompter_editor is not None and self.teleprompter_editor.isVisible():
            self.teleprompter_editor.raise_()
            self.teleprompter_editor.activateWindow()
            return

        if self.teleprompter_editor is None:
            self.teleprompter_editor = TeleprompterEditorDialog(
                current_text=self.settings.teleprompter.last_script,
                settings=self.settings.teleprompter,
            )
            app_icon = get_app_icon()
            if not app_icon.isNull():
                self.teleprompter_editor.setWindowIcon(app_icon)
            self.teleprompter_editor.settings_applied.connect(self._on_teleprompter_applied)
            self.teleprompter_editor.test_requested.connect(self._on_teleprompter_test)
            self.teleprompter_editor.stop_test_requested.connect(self._on_teleprompter_stop_test)
            self.teleprompter_editor.finished.connect(lambda: self.hotkey_service.set_text_input_active(False))
        else:
            self.teleprompter_editor.update_from_settings(self.settings.teleprompter)

        # Ubicar el panel del teleprompter por debajo de la barra flotante para no tapar los botones superiores
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            dlg_w = self.teleprompter_editor.width()
            dlg_h = self.teleprompter_editor.height()
            x = geom.x() + (geom.width() - dlg_w) // 2
            tb_bottom = self.toolbar.y() + self.toolbar.height()
            y = max(tb_bottom + 25, geom.y() + 120)
            if y + dlg_h > geom.bottom():
                y = max(geom.y(), geom.bottom() - dlg_h - 15)
            self.teleprompter_editor.move(x, y)

        self.hotkey_service.set_text_input_active(True)
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
        self.teleprompter_widget.reset_scroll()
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
        self.controller.set_camera_enabled(False)
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
        """Abre el explorador de archivos (Guardar como) para que el usuario elija directorio y nombre de manera fluida e instantánea."""
        # 1. Drenar eventos pendientes en el ciclo de Qt para garantizar respuesta inmediata y 0 lag
        QApplication.processEvents()

        # 2. Asegurar que la carpeta por defecto Videos/RecordMe exista siempre
        default_dir = get_default_recordings_dir()
        default_dir.mkdir(parents=True, exist_ok=True)

        # 3. Desactivar atajos de teclado mientras el diálogo de guardado esté activo
        self.hotkey_service.set_text_input_active(True)
        try:
            suggested_path = str(output_path.resolve())
            selected_path_str, _ = QFileDialog.getSaveFileName(
                None,  # Usar ventana de nivel superior para que Windows no herede flags de Tool flotante
                caption=tr("save_dialog_title"),
                dir=suggested_path,
                filter=f"{tr('save_dialog_filter')};;All Files (*.*)",
            )
        finally:
            self.hotkey_service.set_text_input_active(False)
            QApplication.processEvents()

        if selected_path_str:
            target_path = Path(selected_path_str)
            # Asegurar extensión .mp4
            if not target_path.suffix:
                target_path = target_path.with_suffix(".mp4")

            target_path.parent.mkdir(parents=True, exist_ok=True)

            if target_path.resolve() != output_path.resolve():
                try:
                    if target_path.exists():
                        target_path.unlink()
                    shutil.move(str(output_path), str(target_path))
                    logger.info("Video guardado y renombrado exitosamente por el usuario en: %s", target_path)
                except Exception as e:
                    logger.error("Error al mover el archivo al destino elegido: %s", e)
            else:
                logger.info("Video guardado en la ruta elegida: %s", target_path)
        else:
            logger.info("El usuario canceló el diálogo de guardado. El video se conserva en: %s", output_path)

        if self.session_manager.state == SessionState.DONE:
            self.session_manager.transition_to(SessionState.IDLE)

    def _on_recording_failed(self, error: str) -> None:
        """Muestra error en caso de fallo durante la grabación."""
        QMessageBox.critical(
            self.toolbar,
            APP_NAME,
            tr("recording_error_msg", err=error),
        )
        if self.session_manager.state == SessionState.ERROR:
            self.session_manager.transition_to(SessionState.IDLE)

    def show(self) -> None:
        """Muestra la barra flotante y le otorga foco activo."""
        self.toolbar.show()
        self.toolbar.raise_()
        self.toolbar.activateWindow()


def create_app(argv: list[str] | None = None) -> tuple[QApplication, RecordMeApp]:
    """Crea e inicializa la aplicación Qt y su controlador principal."""
    if argv is None:
        argv = sys.argv

    platform_services = get_platform_services()
    platform_services.set_dpi_awareness()
    setup_app_user_model_id()

    app = QApplication(argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)

    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    # Filtro global de cursor para asegurar que todos los botones tengan la mano indicadora (pointer)
    cursor_filter = ButtonCursorEventFilter(app)
    app.installEventFilter(cursor_filter)

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
