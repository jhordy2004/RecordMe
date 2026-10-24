"""Barra de controles flotante compacta (modo configuración y modo grabación)."""

import logging

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QHideEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QWidget,
)

from recordme.constants import APP_NAME
from recordme.core.events import SessionState
from recordme.core.session import SessionManager
from recordme.platform_services.factory import get_platform_services
from recordme.resources import get_app_logo_pixmap
from recordme.utils.geometry import Rect, get_primary_screen_physical_rect
from recordme.utils.i18n import tr

logger = logging.getLogger(__name__)


class ToolbarHoverBadge(QFrame):
    """Etiqueta flotante de alto contraste que aparece sobre los botones al pasar el cursor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.platform_services = get_platform_services()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        self._action_label = QLabel(self)
        self._action_label.setStyleSheet("color: #FFFFFF; font-size: 11px; font-weight: bold; background: transparent;")
        layout.addWidget(self._action_label)

        self._key_badge = QLabel(self)
        self._key_badge.setStyleSheet(
            "color: #00E5FF; font-size: 11px; font-weight: bold; background: #222222; "
            "padding: 1px 6px; border-radius: 3px; border: 1px solid #444444;"
        )
        layout.addWidget(self._key_badge)

        self.setStyleSheet(
            """
            QFrame {
                background-color: #121212;
                border: 1px solid #444444;
                border-radius: 6px;
            }
            """
        )

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)

    def show_for_widget(self, target: QWidget, action_text: str, key_text: str = "") -> None:
        """Muestra la etiqueta de alto contraste posicionada exactamente sobre el widget objetivo."""
        self._action_label.setText(action_text)
        if key_text:
            self._key_badge.setText(key_text)
            self._key_badge.setVisible(True)
        else:
            self._key_badge.setVisible(False)
        self.adjustSize()

        target_pos = target.mapToGlobal(QPoint(0, 0))
        target_w = target.width()
        badge_w = self.width()
        badge_h = self.height()

        x = target_pos.x() + (target_w - badge_w) // 2
        y = target_pos.y() - badge_h - 6  # 6 píxeles arriba del botón

        if y < 0:
            y = target_pos.y() + target.height() + 6

        self.move(x, y)
        self.show()
        self.raise_()

    def hide_badge(self) -> None:
        """Oculta la etiqueta flotante."""
        self.hide()


class FloatingToolbar(QWidget):
    """Barra flotante compacta con controles de grabación y exclusión de pantalla."""

    request_region_selection = Signal()
    request_start_record = Signal()
    request_pause_record = Signal()
    request_resume_record = Signal()
    request_stop_record = Signal()
    mic_settings_requested = Signal()
    mic_toggled = Signal(bool)
    camera_toggled = Signal(bool)
    teleprompter_clicked = Signal()
    censor_clicked = Signal()
    request_exit = Signal()
    escape_pressed = Signal()
    _session_state_changed_signal = Signal(object, object)

    def __init__(self, session_manager: SessionManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session_manager = session_manager
        self.platform_services = get_platform_services()

        self._drag_start_pos: QPoint | None = None
        self._elapsed_seconds = 0
        self._mic_enabled = True
        self._cam_enabled = False
        self._selected_region: Rect = get_primary_screen_physical_rect()

        # Configuración visual flotante
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_timer_tick)

        self._hover_badge = ToolbarHoverBadge(self)

        self._init_ui()
        self._session_state_changed_signal.connect(self._on_session_state_changed)
        self.session_manager.add_listener(self._session_state_changed_signal.emit)

    def _init_ui(self) -> None:
        """Construye la interfaz de la barra con tema oscuro y bordes redondeados."""
        self.layout_main = QHBoxLayout(self)
        self.layout_main.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.layout_main.setContentsMargins(14, 8, 14, 8)
        self.layout_main.setSpacing(10)

        # Logotipo oficial de RecordMe en su tamaño real original (114x38 px)
        self.app_logo = QLabel()
        logo_pix = get_app_logo_pixmap()
        if not logo_pix.isNull():
            self.app_logo.setPixmap(logo_pix)
        else:
            self.app_logo.setText(APP_NAME)
            title_font = QFont()
            title_font.setBold(True)
            title_font.setPointSize(11)
            self.app_logo.setFont(title_font)
            self.app_logo.setStyleSheet("color: #FFFFFF;")
        self.app_title = self.app_logo
        self.layout_main.addWidget(self.app_logo)

        # Etiqueta de área seleccionada
        self.area_label = QLabel(f"{self._selected_region.width}×{self._selected_region.height}")
        self.area_label.setStyleSheet("color: #00B4D8; font-size: 11px;")
        self.layout_main.addWidget(self.area_label)

        # Etiqueta de zoom dinámico
        self.zoom_badge = QLabel("🔍 100%")
        self.zoom_badge.setToolTip(tr("zoom_badge_tooltip"))
        self.zoom_badge.setStyleSheet(
            "color: #AAAAAA; font-size: 11px; padding: 3px 6px; background: #262626; border-radius: 4px;"
        )
        self.layout_main.addWidget(self.zoom_badge)

        # Botón Seleccionar Área
        self.btn_area = QPushButton(tr("tb_area"))
        self.btn_area.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_area.setMinimumWidth(80)
        self.btn_area.setStyleSheet(self._button_style("#333333", "#444444"))
        self.btn_area.clicked.connect(self.request_region_selection.emit)
        self.layout_main.addWidget(self.btn_area)

        # Botón Micrófono: al hacer clic abre el panel de configuración de audio
        self.btn_mic = QPushButton()
        self.btn_mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mic.setMinimumWidth(110)
        self.btn_mic.clicked.connect(self.mic_settings_requested.emit)
        self.set_mic_enabled(True)
        self.layout_main.addWidget(self.btn_mic)

        # Botón Cámara
        self.btn_cam = QPushButton()
        self.btn_cam.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cam.setMinimumWidth(95)
        self.btn_cam.clicked.connect(self._toggle_camera)
        self.set_camera_enabled(False)
        self.layout_main.addWidget(self.btn_cam)

        # Botón Teleprompter
        self.btn_teleprompter = QPushButton(tr("tb_teleprompter"))
        self.btn_teleprompter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_teleprompter.setMinimumWidth(105)
        self.btn_teleprompter.setStyleSheet(self._button_style("#333333", "#444444"))
        self.btn_teleprompter.clicked.connect(self.teleprompter_clicked.emit)
        self.layout_main.addWidget(self.btn_teleprompter)

        # Botón Censura en Tiempo Real
        self.btn_censor = QPushButton(tr("tb_censor"))
        self.btn_censor.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_censor.setMinimumWidth(90)
        self.btn_censor.setStyleSheet(self._button_style("#333333", "#444444"))
        self.btn_censor.clicked.connect(self.censor_clicked.emit)
        self.layout_main.addWidget(self.btn_censor)

        # Temporizador (visible durante grabación)
        self.timer_label = QLabel("00:00")
        timer_font = QFont("Consolas")
        timer_font.setBold(True)
        timer_font.setPointSize(12)
        self.timer_label.setFont(timer_font)
        self.timer_label.setStyleSheet("color: #FF5252;")
        self.timer_label.setMinimumWidth(55)
        self.timer_label.setVisible(False)
        self.layout_main.addWidget(self.timer_label)

        # Botón Pausar / Reanudar
        self.btn_pause = QPushButton(tr("tb_pause"))
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setMinimumWidth(85)
        self.btn_pause.setStyleSheet(self._button_style("#E67E22", "#D35400"))
        self.btn_pause.setVisible(False)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.layout_main.addWidget(self.btn_pause)

        # Botón Principal (Grabar / Detener)
        self.btn_record = QPushButton(tr("tb_record"))
        self.btn_record.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_record.setMinimumWidth(85)
        self.btn_record.setStyleSheet(self._button_style("#E50914", "#FF1E27"))
        self.btn_record.clicked.connect(self._on_record_clicked)
        self.layout_main.addWidget(self.btn_record)

        # Botón Cerrar Aplicación (✕ Salir)
        self.btn_close_app = QPushButton(tr("tb_exit"))
        self.btn_close_app.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close_app.setMinimumWidth(70)
        self.btn_close_app.setToolTip(tr("tb_exit_tooltip"))
        self.btn_close_app.setStyleSheet(
            """
            QPushButton {
                background-color: #5A1015;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
                min-width: 65px;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
            QPushButton:pressed {
                background-color: #380004;
            }
            """
        )
        self.btn_close_app.clicked.connect(self.request_exit.emit)
        self.layout_main.addWidget(self.btn_close_app)

        self.update_tooltips()
        self._install_hover_events()
        self.adjustSize()

    def _install_hover_events(self) -> None:
        """Instala filtros de eventos en cada botón para mostrar el badge flotante inmediatamente."""
        self._monitored_widgets = [
            self.btn_area,
            self.btn_mic,
            self.btn_cam,
            self.btn_teleprompter,
            self.btn_censor,
            self.btn_pause,
            self.btn_record,
            self.btn_close_app,
            self.zoom_badge,
        ]
        for w in self._monitored_widgets:
            w.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """Detecta entrada y salida del cursor en cada botón para desplegar la etiqueta de ayuda."""
        if event.type() == QEvent.Type.Enter:
            self._show_badge_for(watched)
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress):
            if hasattr(self, "_hover_badge"):
                self._hover_badge.hide_badge()
        try:
            return super().eventFilter(watched, event)
        except (TypeError, RuntimeError):
            return False

    def _show_badge_for(self, widget: QObject) -> None:
        """Despliega la etiqueta flotante superior de alto contraste con 'Atajo' y la tecla correspondiente."""
        if not hasattr(self, "_hover_badge") or not widget.isWidgetType():
            return

        shortcut_label = tr("tb_shortcut")

        if widget == self.btn_area:
            self._hover_badge.show_for_widget(self.btn_area, shortcut_label, "Alt+L")
        elif widget == self.btn_mic:
            self._hover_badge.show_for_widget(self.btn_mic, shortcut_label, "Alt+M")
        elif widget == self.btn_cam:
            self._hover_badge.show_for_widget(self.btn_cam, shortcut_label, "Alt+C")
        elif widget == self.btn_teleprompter:
            self._hover_badge.show_for_widget(self.btn_teleprompter, shortcut_label, "Alt+T")
        elif widget == self.btn_censor:
            self._hover_badge.show_for_widget(self.btn_censor, shortcut_label, "Alt+X")
        elif widget == self.btn_pause:
            self._hover_badge.show_for_widget(self.btn_pause, shortcut_label, "Alt+P")
        elif widget == self.btn_record:
            self._hover_badge.show_for_widget(self.btn_record, shortcut_label, "Alt+R")
        elif widget == self.btn_close_app:
            self._hover_badge.show_for_widget(self.btn_close_app, shortcut_label, "Alt+Q")
        elif widget == self.zoom_badge:
            self._hover_badge.show_for_widget(self.zoom_badge, shortcut_label, "Alt +, Alt -")

    def _button_style(self, bg_normal: str, bg_hover: str) -> str:
        """Genera hojas de estilo CSS para botones redondeados modernos."""
        return f"""
            QPushButton {{
                background-color: {bg_normal};
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
            }}
            QPushButton:pressed {{
                background-color: #111111;
            }}
        """

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Pinta el fondo redondeado translúcido de la barra."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(24, 24, 24, 235))
        painter.setPen(QColor(60, 60, 60, 180))
        painter.drawRoundedRect(self.rect(), 10, 10)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Aplica la exclusión de captura nativa para que la barra no aparezca en los videos."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)
        self.platform_services.apply_blur_behind(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Permite arrastrar la barra haciendo clic en cualquier parte libre y activa foco."""
        self.activateWindow()
        self.setFocus()
        if hasattr(self, "_hover_badge"):
            self._hover_badge.hide_badge()
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Mueve la barra junto al cursor."""
        if hasattr(self, "_hover_badge"):
            self._hover_badge.hide_badge()
        if self._drag_start_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finaliza el arrastre."""
        self._drag_start_pos = None

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Emite escape_pressed si se presiona la tecla Escape con la barra enfocada."""
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        """Oculta la etiqueta al ocultar la barra."""
        super().hideEvent(event)
        if hasattr(self, "_hover_badge"):
            self._hover_badge.hide_badge()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Cierra la etiqueta flotante al destruir la barra."""
        self.session_manager.remove_listener(self._session_state_changed_signal.emit)
        if hasattr(self, "_hover_badge"):
            self._hover_badge.close()
        super().closeEvent(event)

    def update_selected_region(self, region: Rect) -> None:
        """Actualiza la visualización de la resolución seleccionada."""
        self._selected_region = region
        self.area_label.setText(f"{region.width}×{region.height}")
        self.adjustSize()

    def update_zoom_display(self, zoom_level: float) -> None:
        """Actualiza el indicador visual de zoom en la barra."""
        pct = int(round(zoom_level * 100))
        self.zoom_badge.setText(f"🔍 {pct}%")
        if pct > 100:
            self.zoom_badge.setStyleSheet(
                "color: #00E5FF; font-weight: bold; font-size: 11px; padding: 3px 6px; "
                "background: rgba(0, 229, 255, 0.18); border: 1px solid #00E5FF; border-radius: 4px;"
            )
        else:
            self.zoom_badge.setStyleSheet(
                "color: #AAAAAA; font-size: 11px; padding: 3px 6px; background: #262626; border-radius: 4px;"
            )
        self.adjustSize()

    def toggle_mic_mute(self) -> None:
        """Alterna el mute del micrófono (atajo M o Alt+M) sin abrir el panel de configuración."""
        self.set_mic_enabled(not self._mic_enabled)
        self.mic_toggled.emit(self._mic_enabled)

    def _toggle_mic(self) -> None:
        """Alterna el estado del micrófono (compatibilidad con atajos y tests)."""
        self.toggle_mic_mute()

    def set_mic_enabled(self, enabled: bool) -> None:
        """Actualiza el texto y apariencia visual del botón de micrófono."""
        self._mic_enabled = enabled
        status = "On" if self._mic_enabled else "Off"
        self.btn_mic.setText(f"{tr('tb_microphone')}: {status}")
        if self._mic_enabled:
            # Micrófono activo: verde visible
            self.btn_mic.setStyleSheet(self._button_style("#1B5E20", "#2E7D32"))
        else:
            # Micrófono apagado / silenciado: rojo oscuro
            self.btn_mic.setStyleSheet(self._button_style("#5A1015", "#7A1C22"))
        self.adjustSize()

    def _toggle_camera(self) -> None:
        """Notifica solicitud de alternar cámara."""
        self.camera_toggled.emit(not self._cam_enabled)

    def set_camera_enabled(self, enabled: bool) -> None:
        """Actualiza el botón y estado de la cámara."""
        self._cam_enabled = enabled
        status = "On" if self._cam_enabled else "Off"
        self.btn_cam.setText(f"{tr('tb_camera')}: {status}")
        self.btn_cam.setStyleSheet(
            self._button_style("#007ACC", "#0098FF")
            if self._cam_enabled
            else self._button_style("#333333", "#444444")
        )
        self.adjustSize()

    def update_tooltips(self) -> None:
        """Limpia los tooltips nativos inferiores para mostrar únicamente el badge superior de alto contraste."""
        self.btn_area.setToolTip("")
        self.btn_mic.setToolTip("")
        self.btn_cam.setToolTip("")
        self.btn_teleprompter.setToolTip("")
        self.btn_censor.setToolTip("")
        self.zoom_badge.setToolTip("")
        self.btn_pause.setToolTip("")
        self.btn_record.setToolTip("")
        self.btn_close_app.setToolTip("")

    def _on_record_clicked(self) -> None:
        """Maneja el clic del botón principal (Grabar o Detener)."""
        if self.session_manager.state in (SessionState.RECORDING, SessionState.PAUSED, SessionState.COUNTDOWN):
            # Detener el contador inmediatamente al solicitar la finalización
            self._timer.stop()
            self.btn_pause.setVisible(False)
            self.btn_record.setText(tr("tb_saving"))
            self.btn_record.setEnabled(False)
            self.btn_record.setStyleSheet(self._button_style("#7F8C8D", "#95A5A6"))
            self.request_stop_record.emit()
        else:
            self.request_start_record.emit()

    def _toggle_pause(self) -> None:
        """Alterna entre pausar y reanudar la grabación."""
        if self.session_manager.state in (SessionState.RECORDING, SessionState.COUNTDOWN):
            self.request_pause_record.emit()
        elif self.session_manager.state == SessionState.PAUSED:
            self.request_resume_record.emit()

    def _on_timer_tick(self) -> None:
        """Actualiza el contador de tiempo de grabación transcurrido."""
        self._elapsed_seconds += 1
        mins = self._elapsed_seconds // 60
        secs = self._elapsed_seconds % 60
        self.timer_label.setText(f"{mins:02d}:{secs:02d}")

    def _on_session_state_changed(self, old_state: SessionState, new_state: SessionState) -> None:
        """Adapta la visibilidad de botones según el estado de la sesión."""
        if new_state in (SessionState.RECORDING, SessionState.COUNTDOWN):
            self.btn_area.setVisible(False)
            self.timer_label.setVisible(True)
            self.btn_pause.setVisible(True)
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText(tr("tb_pause"))
            self.btn_record.setText(tr("tb_stop"))
            self.btn_record.setEnabled(True)
            self.btn_record.setStyleSheet(self._button_style("#C0392B", "#962D22"))
            self.update_tooltips()
            if new_state == SessionState.RECORDING:
                # Solo reiniciar contador si es una nueva grabación, no al reanudar de pausa
                if old_state != SessionState.PAUSED:
                    self._elapsed_seconds = 0
                    self.timer_label.setText("00:00")
                if not self._timer.isActive():
                    self._timer.start()
            else:
                self.timer_label.setText("00:00")
        elif new_state == SessionState.PAUSED:
            self.btn_pause.setText(tr("tb_resume"))
            self.update_tooltips()
            self._timer.stop()
        elif new_state in (SessionState.IDLE, SessionState.DONE, SessionState.ERROR):
            self._timer.stop()
            self.btn_area.setVisible(True)
            self.timer_label.setVisible(False)
            self.btn_pause.setVisible(False)
            self.btn_record.setText(tr("tb_record"))
            self.btn_record.setEnabled(True)
            self.btn_record.setStyleSheet(self._button_style("#E50914", "#FF1E27"))
            self.update_tooltips()
        elif new_state == SessionState.FINALIZING:
            self._timer.stop()
            self.btn_pause.setVisible(False)
            self.btn_record.setText(tr("tb_saving"))
            self.btn_record.setEnabled(False)
            self.btn_record.setStyleSheet(self._button_style("#7F8C8D", "#95A5A6"))
        self.adjustSize()
