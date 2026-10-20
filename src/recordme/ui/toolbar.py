"""Barra de controles flotante compacta (modo configuración y modo grabación)."""

import logging

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent, QShowEvent, QWheelEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from recordme.constants import APP_NAME
from recordme.core.events import SessionState
from recordme.core.session import SessionManager
from recordme.platform_services.factory import get_platform_services
from recordme.utils.geometry import Rect, get_primary_screen_physical_rect

logger = logging.getLogger(__name__)


class FloatingToolbar(QWidget):
    """Barra flotante compacta con controles de grabación y exclusión de pantalla."""

    request_region_selection = Signal()
    request_start_record = Signal()
    request_pause_record = Signal()
    request_resume_record = Signal()
    request_stop_record = Signal()
    mic_toggled = Signal(bool)
    camera_toggled = Signal(bool)
    teleprompter_clicked = Signal()
    zoom_changed = Signal(float)
    censor_clicked = Signal()
    request_exit = Signal()

    def __init__(self, session_manager: SessionManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session_manager = session_manager
        self.platform_services = get_platform_services()

        self._drag_start_pos: QPoint | None = None
        self._elapsed_seconds = 0
        self._mic_enabled = True
        self._cam_enabled = False
        self._zoom_level = 1.0
        self._selected_region: Rect = get_primary_screen_physical_rect()

        # Configuración visual flotante
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_timer_tick)

        self._init_ui()
        self.session_manager.add_listener(self._on_session_state_changed)

    def _init_ui(self) -> None:
        """Construye la interfaz de la barra con tema oscuro y bordes redondeados."""
        self.layout_main = QHBoxLayout(self)
        self.layout_main.setContentsMargins(14, 8, 14, 8)
        self.layout_main.setSpacing(10)

        # Nombre / Ícono de la app
        self.app_title = QLabel(APP_NAME)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.app_title.setFont(title_font)
        self.app_title.setStyleSheet("color: #FFFFFF;")
        self.layout_main.addWidget(self.app_title)

        # Etiqueta de área seleccionada
        self.area_label = QLabel(f"{self._selected_region.width}×{self._selected_region.height}")
        self.area_label.setStyleSheet("color: #00B4D8; font-size: 11px;")
        self.layout_main.addWidget(self.area_label)

        # Botón Seleccionar Área
        self.btn_area = QPushButton("Área")
        self.btn_area.setStyleSheet(self._button_style("#333333", "#444444"))
        self.btn_area.clicked.connect(self.request_region_selection.emit)
        self.layout_main.addWidget(self.btn_area)

        # Botón Micrófono
        self.btn_mic = QPushButton("Mic: On")
        self.btn_mic.setStyleSheet(self._button_style("#333333", "#444444"))
        self.btn_mic.clicked.connect(self._toggle_mic)
        self.layout_main.addWidget(self.btn_mic)

        # Botón Cámara
        self.btn_cam = QPushButton("Cámara: Off")
        self.btn_cam.setStyleSheet(self._button_style("#333333", "#444444"))
        self.btn_cam.clicked.connect(self._toggle_camera)
        self.layout_main.addWidget(self.btn_cam)

        # Botón Teleprompter
        self.btn_teleprompter = QPushButton("Teleprompter")
        self.btn_teleprompter.setStyleSheet(self._button_style("#333333", "#444444"))
        self.btn_teleprompter.clicked.connect(self.teleprompter_clicked.emit)
        self.layout_main.addWidget(self.btn_teleprompter)

        # Botón Zoom en Vivo
        self.btn_zoom = QPushButton("Zoom: 1.0x")
        self.btn_zoom.setStyleSheet(self._button_style("#333333", "#444444"))
        self.btn_zoom.setToolTip("Alternar o ajustar zoom con clic o rueda del ratón")
        self.btn_zoom.clicked.connect(self._toggle_zoom)
        self.layout_main.addWidget(self.btn_zoom)

        # Botón Censura en Tiempo Real
        self.btn_censor = QPushButton("Censura")
        self.btn_censor.setStyleSheet(self._button_style("#333333", "#444444"))
        self.btn_censor.setToolTip("Definir o editar áreas de censura (blur/pixelado)")
        self.btn_censor.clicked.connect(self.censor_clicked.emit)
        self.layout_main.addWidget(self.btn_censor)

        # Temporizador (visible durante grabación)
        self.timer_label = QLabel("00:00")
        timer_font = QFont("Consolas")
        timer_font.setBold(True)
        timer_font.setPointSize(12)
        self.timer_label.setFont(timer_font)
        self.timer_label.setStyleSheet("color: #FF5252;")
        self.timer_label.setVisible(False)
        self.layout_main.addWidget(self.timer_label)

        # Botón Pausar / Reanudar
        self.btn_pause = QPushButton("Pausar")
        self.btn_pause.setStyleSheet(self._button_style("#E67E22", "#D35400"))
        self.btn_pause.setVisible(False)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.layout_main.addWidget(self.btn_pause)

        # Botón Principal (Grabar / Detener)
        self.btn_record = QPushButton("Grabar")
        self.btn_record.setStyleSheet(self._button_style("#E50914", "#FF1E27"))
        self.btn_record.clicked.connect(self._on_record_clicked)
        self.layout_main.addWidget(self.btn_record)

        # Botón Cerrar Aplicación (✕ Salir)
        self.btn_close_app = QPushButton("✕ Salir")
        self.btn_close_app.setToolTip("Cerrar RecordMe")
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

        self.adjustSize()

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
        """Permite arrastrar la barra haciendo clic en cualquier parte libre."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Mueve la barra junto al cursor."""
        if self._drag_start_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finaliza el arrastre."""
        self._drag_start_pos = None

    def update_selected_region(self, region: Rect) -> None:
        """Actualiza la visualización de la resolución seleccionada."""
        self._selected_region = region
        self.area_label.setText(f"{region.width}×{region.height}")
        self.adjustSize()

    def _toggle_mic(self) -> None:
        """Alterna el estado del micrófono."""
        self._mic_enabled = not self._mic_enabled
        self.btn_mic.setText("Mic: On" if self._mic_enabled else "Mic: Mute")
        self.btn_mic.setStyleSheet(
            self._button_style("#333333", "#444444")
            if self._mic_enabled
            else self._button_style("#721C24", "#F8D7DA")
        )
        self.mic_toggled.emit(self._mic_enabled)

    def _toggle_camera(self) -> None:
        """Alterna el estado de la cámara."""
        self.set_camera_enabled(not self._cam_enabled)
        self.camera_toggled.emit(self._cam_enabled)

    def set_camera_enabled(self, enabled: bool) -> None:
        """Actualiza el botón y estado de la cámara."""
        self._cam_enabled = enabled
        self.btn_cam.setText("Cámara: On" if self._cam_enabled else "Cámara: Off")
        self.btn_cam.setStyleSheet(
            self._button_style("#007ACC", "#0098FF")
            if self._cam_enabled
            else self._button_style("#333333", "#444444")
        )

    def _toggle_zoom(self) -> None:
        """Alterna el nivel de zoom entre 1.0x y 2.0x."""
        if self._zoom_level <= 1.05:
            self.set_zoom_level(2.0)
        else:
            self.set_zoom_level(1.0)

    def set_zoom_level(self, level: float) -> None:
        """Actualiza el nivel de zoom mostrado en el botón y emite la señal."""
        self._zoom_level = max(1.0, min(level, 4.0))
        self.btn_zoom.setText(f"Zoom: {self._zoom_level:.1f}x")
        if self._zoom_level > 1.05:
            self.btn_zoom.setStyleSheet(self._button_style("#007ACC", "#0098FF"))
        else:
            self.btn_zoom.setStyleSheet(self._button_style("#333333", "#444444"))
        self.zoom_changed.emit(self._zoom_level)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Permite ajustar el nivel de zoom con la rueda del ratón al apuntar a la barra."""
        delta = event.angleDelta().y()
        if delta != 0:
            step = 0.25 if delta > 0 else -0.25
            self.set_zoom_level(self._zoom_level + step)
            event.accept()
        else:
            super().wheelEvent(event)

    def _on_record_clicked(self) -> None:
        """Maneja el clic del botón principal (Grabar o Detener)."""
        if self.session_manager.state in (SessionState.RECORDING, SessionState.PAUSED):
            self.request_stop_record.emit()
        else:
            self.request_start_record.emit()

    def _toggle_pause(self) -> None:
        """Alterna entre pausar y reanudar la grabación."""
        if self.session_manager.state == SessionState.RECORDING:
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
        if new_state == SessionState.RECORDING:
            self.btn_area.setVisible(False)
            self.timer_label.setVisible(True)
            self.btn_pause.setVisible(True)
            self.btn_pause.setText("Pausar")
            self.btn_record.setText("Detener")
            self.btn_record.setStyleSheet(self._button_style("#C0392B", "#962D22"))
            if not self._timer.isActive():
                self._elapsed_seconds = 0
                self._timer.start()
        elif new_state == SessionState.PAUSED:
            self.btn_pause.setText("Reanudar")
            self._timer.stop()
        elif new_state == SessionState.COUNTDOWN:
            self.btn_record.setText("3...")
            self.btn_record.setEnabled(False)
        elif new_state in (SessionState.IDLE, SessionState.DONE, SessionState.ERROR):
            self._timer.stop()
            self.btn_area.setVisible(True)
            self.timer_label.setVisible(False)
            self.btn_pause.setVisible(False)
            self.btn_record.setText("Grabar")
            self.btn_record.setEnabled(True)
            self.btn_record.setStyleSheet(self._button_style("#E50914", "#FF1E27"))
        elif new_state == SessionState.FINALIZING:
            self.btn_record.setText("Guardando...")
            self.btn_record.setEnabled(False)
        self.adjustSize()
