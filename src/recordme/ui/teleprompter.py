"""Ventana flotante de teleprompter con scroll suave continuo, controles de lectura y exclusión de captura."""

import logging
import time

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from recordme.config.settings import TeleprompterSettings
from recordme.platform_services.factory import get_platform_services

logger = logging.getLogger(__name__)


class TeleprompterWidget(QWidget):
    """Panel flotante con desplazamiento continuo subpíxel por tiempo y efecto translúcido."""

    closed = Signal()

    def __init__(
        self,
        text: str,
        settings: TeleprompterSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.raw_text = text
        self.settings = settings
        self.platform_services = get_platform_services()

        self._lines: list[str] = []
        self._line_height: int = 44
        self._scroll_offset_y: float = 0.0

        self._is_scrolling = False
        self._is_paused = False
        self._last_tick_time: float = 0.0
        self._drag_start_pos: QPoint | None = None

        # Configuración de ventana flotante
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        # Timer de animación a 60 FPS
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        self._init_ui()
        self._prepare_text_lines()
        self._setup_geometry()

    def _init_ui(self) -> None:
        """Construye el layout con la barra de control inferior (Play/Pause, Reiniciar, Cerrar)."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 8)
        main_layout.setSpacing(6)

        # Espacio flexible superior donde se dibuja el texto en paintEvent
        main_layout.addStretch(1)

        # Barra de controles en la parte inferior del panel
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setContentsMargins(6, 0, 6, 0)
        ctrl_bar.setSpacing(8)

        # Botón Play / Pause
        self.btn_play_pause = QPushButton("▶ Iniciar")
        self.btn_play_pause.setStyleSheet(self._button_style("#007ACC", "#0098FF"))
        self.btn_play_pause.clicked.connect(self._toggle_playback)
        ctrl_bar.addWidget(self.btn_play_pause)

        # Botón Reiniciar
        self.btn_rewind = QPushButton("🔄 Inicio")
        self.btn_rewind.setStyleSheet(self._button_style("#333333", "#444444"))
        self.btn_rewind.clicked.connect(self.reset_scroll)
        ctrl_bar.addWidget(self.btn_rewind)

        ctrl_bar.addStretch(1)

        # Botón Cerrar
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedWidth(28)
        self.btn_close.setStyleSheet(self._button_style("#444444", "#C0392B"))
        self.btn_close.clicked.connect(self._on_close_clicked)
        ctrl_bar.addWidget(self.btn_close)

        main_layout.addLayout(ctrl_bar)

    def _button_style(self, bg_normal: str, bg_hover: str) -> str:
        """Estilo de botones compactos integrados."""
        return f"""
            QPushButton {{
                background-color: {bg_normal};
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
            }}
        """

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Aplica la exclusión nativa de captura para que el teleprompter sea 100% invisible en el video."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)
        self.platform_services.apply_blur_behind(self)

    def set_script(self, text: str) -> None:
        """Actualiza el texto del guion y recalcula las líneas."""
        self.raw_text = text
        self._scroll_offset_y = 0.0
        self._prepare_text_lines()
        self.update()

    def update_settings(self, settings: TeleprompterSettings) -> None:
        """Aplica nuevos ajustes de tamaño de fuente, velocidad o líneas visibles."""
        self.settings = settings
        self._prepare_text_lines()
        self._setup_geometry()
        self.update()

    def start_scrolling(self) -> None:
        """Inicia el auto-scroll del texto."""
        self._is_scrolling = True
        self._is_paused = False
        self._last_tick_time = time.perf_counter()
        self.btn_play_pause.setText("⏸ Pausar")
        self.btn_play_pause.setStyleSheet(self._button_style("#E67E22", "#D35400"))
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        logger.info("Teleprompter scrolling iniciado (%.1f seg/línea).", self.settings.seconds_per_line)

    def pause_scrolling(self) -> None:
        """Pausa el avance del texto."""
        self._is_paused = True
        self.btn_play_pause.setText("▶ Reanudar")
        self.btn_play_pause.setStyleSheet(self._button_style("#007ACC", "#0098FF"))

    def resume_scrolling(self) -> None:
        """Reanuda el avance del texto."""
        self._is_paused = False
        self._last_tick_time = time.perf_counter()
        self.btn_play_pause.setText("⏸ Pausar")
        self.btn_play_pause.setStyleSheet(self._button_style("#E67E22", "#D35400"))

    def reset_scroll(self) -> None:
        """Reinicia el texto al comienzo."""
        self._scroll_offset_y = 0.0
        self._last_tick_time = time.perf_counter()
        self.update()

    def _toggle_playback(self) -> None:
        """Alterna entre reproducción y pausa."""
        if not self._is_scrolling or self._is_paused:
            if not self._is_scrolling:
                self.start_scrolling()
            else:
                self.resume_scrolling()
        else:
            self.pause_scrolling()

    def _on_close_clicked(self) -> None:
        """Oculta el widget y emite señal de cerrado."""
        self.pause_scrolling()
        self.hide()
        self.closed.emit()

    def _prepare_text_lines(self) -> None:
        """Divide el texto aplicando word-wrap generoso para que ninguna palabra quede cortada."""
        font = QFont("Segoe UI", self.settings.font_size)
        font.setBold(True)
        fm = QFontMetrics(font)
        self._line_height = int(fm.height() * 1.4)

        screen = self.screen()
        screen_w = screen.geometry().width() if screen else 1920
        widget_w = int(screen_w * (self.settings.width_pct / 100.0))
        # Margen lateral amplio (40px a cada lado) para evitar cualquier recorte en bordes
        text_w = max(200, widget_w - 80)

        raw_lines: list[str] = []
        for paragraph in self.raw_text.splitlines():
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            words = paragraph.split()
            current_line = ""
            for word in words:
                candidate = f"{current_line} {word}".strip()
                if fm.horizontalAdvance(candidate) <= text_w:
                    current_line = candidate
                else:
                    if current_line:
                        raw_lines.append(current_line)
                    current_line = word
            if current_line:
                raw_lines.append(current_line)

        # Líneas de respiro inicial para que la primera palabra comience centrada y cómoda
        self._lines = ["", *raw_lines, "", ""]

    def _setup_geometry(self) -> None:
        """Calcula el tamaño del panel según las líneas visibles + el espacio para la barra de control."""
        screen = self.screen()
        if screen:
            geom = screen.geometry()
            w = int(geom.width() * (self.settings.width_pct / 100.0))
            # Altura para las líneas de texto visibles + 46px para márgenes y botones
            h = int(self._line_height * self.settings.lines_visible + 46)
            x = geom.x() + int((geom.width() - w) * self.settings.position_x)
            y = geom.y() + int(geom.height() * self.settings.position_y)
            self.setGeometry(x, y, w, h)
        else:
            self.resize(800, int(self._line_height * self.settings.lines_visible + 46))

    def _on_anim_tick(self) -> None:
        """Calcula el avance temporal subpíxel basado en los segundos por línea configurados."""
        now = time.perf_counter()
        dt = now - self._last_tick_time
        self._last_tick_time = now

        if self._is_scrolling and not self._is_paused and len(self._lines) > 0:
            sec_per_line = max(0.5, self.settings.seconds_per_line)
            pixels_per_second = self._line_height / sec_per_line

            self._scroll_offset_y += pixels_per_second * dt

            # Detener suavemente al llegar al final
            total_height = len(self._lines) * self._line_height
            if self._scroll_offset_y > total_height:
                self._is_scrolling = False
                self._is_paused = False
                self._anim_timer.stop()
                self.btn_play_pause.setText("▶ Iniciar")
                self.btn_play_pause.setStyleSheet(self._button_style("#007ACC", "#0098FF"))

            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Dibuja el fondo acrílico oscuro y las líneas de texto con legibilidad completa."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Fondo translúcido con esquinas redondeadas
        alpha = int(self.settings.opacity * 255)
        painter.setBrush(QColor(16, 16, 16, alpha))
        painter.setPen(QColor(255, 255, 255, 30))
        painter.drawRoundedRect(self.rect(), 12, 12)

        # Área de renderizado del texto (dejando libre la barra de botones inferior)
        margin_x = 24
        margin_top = 8
        text_area_height = self.height() - 40
        content_rect = QRect(margin_x, margin_top, self.width() - margin_x * 2, text_area_height)

        painter.save()
        painter.setClipRect(content_rect)

        font = QFont("Segoe UI", self.settings.font_size)
        font.setBold(True)
        painter.setFont(font)

        # Foco de lectura: centro del área de texto
        focus_y = content_rect.top() + content_rect.height() // 2
        start_y = content_rect.top() - int(self._scroll_offset_y)

        for idx, line in enumerate(self._lines):
            line_y = start_y + (idx * self._line_height)

            # Optimización: no dibujar fuera del rango visible
            if line_y + self._line_height < content_rect.top() - 20:
                continue
            if line_y > content_rect.bottom() + 20:
                break

            if not line:
                continue

            # Resaltar la línea activa y atenuar las anteriores/posteriores suavemente
            dist_to_focus = abs((line_y + self._line_height // 2) - focus_y)
            focus_factor = max(0.40, 1.0 - (dist_to_focus / max(1, content_rect.height() * 0.85)))

            text_color = QColor(255, 255, 255, int(255 * focus_factor))
            painter.setPen(text_color)

            line_rect = QRect(content_rect.left(), line_y, content_rect.width(), self._line_height)
            painter.drawText(line_rect, Qt.AlignmentFlag.AlignCenter, line)

        painter.restore()

        # Difuminado superior muy sutil
        gradient_top = QLinearGradient(0, 0, 0, 14)
        gradient_top.setColorAt(0, QColor(16, 16, 16, alpha))
        gradient_top.setColorAt(1, QColor(16, 16, 16, 0))
        painter.fillRect(QRect(0, 0, self.width(), 14), gradient_top)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Permite mover el teleprompter arrastrando con el botón izquierdo en cualquier parte libre."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Actualiza la posición del teleprompter."""
        if self._drag_start_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finaliza el arrastre."""
        self._drag_start_pos = None

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Permite retroceder o adelantar el texto suavemente con la rueda del ratón."""
        delta = event.angleDelta().y()
        self._scroll_offset_y -= delta * 0.4
        self._scroll_offset_y = max(0.0, self._scroll_offset_y)
        self.update()
        event.accept()
