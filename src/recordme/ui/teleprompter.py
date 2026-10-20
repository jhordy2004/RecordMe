"""Ventana flotante de teleprompter con scroll suave continuo basado en WPM y exclusión de captura."""

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
from PySide6.QtWidgets import QWidget

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
        self._line_height: int = 40
        self._scroll_offset_y: float = 0.0  # Desplazamiento continuo en píxeles

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

        # Timer de animación a ~60 FPS para suavidad absoluta
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        self._prepare_text_lines()
        self._setup_geometry()

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
        """Aplica nuevos ajustes de tamaño de fuente, WPM o líneas visibles."""
        self.settings = settings
        self._prepare_text_lines()
        self._setup_geometry()
        self.update()

    def start_scrolling(self) -> None:
        """Inicia el auto-scroll del texto."""
        self._is_scrolling = True
        self._is_paused = False
        self._last_tick_time = time.perf_counter()
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        logger.info("Teleprompter scrolling iniciado a %d WPM.", self.settings.wpm)

    def pause_scrolling(self) -> None:
        """Pausa el avance del texto."""
        self._is_paused = True

    def resume_scrolling(self) -> None:
        """Reanuda el avance del texto."""
        self._is_paused = False
        self._last_tick_time = time.perf_counter()

    def reset_scroll(self) -> None:
        """Reinicia el texto al comienzo."""
        self._scroll_offset_y = 0.0
        self._last_tick_time = time.perf_counter()
        self.update()

    def _prepare_text_lines(self) -> None:
        """Divide el texto aplicando word-wrap según el ancho útil del widget y calcula alturas."""
        font = QFont("Segoe UI", self.settings.font_size)
        fm = QFontMetrics(font)
        self._line_height = int(fm.height() * 1.3)

        screen = self.screen()
        screen_w = screen.geometry().width() if screen else 1920
        widget_w = int(screen_w * (self.settings.width_pct / 100.0))
        text_w = max(200, widget_w - 48)

        self._lines = []
        for paragraph in self.raw_text.splitlines():
            paragraph = paragraph.strip()
            if not paragraph:
                self._lines.append("")
                continue

            words = paragraph.split()
            current_line = ""
            for word in words:
                candidate = f"{current_line} {word}".strip()
                if fm.horizontalAdvance(candidate) <= text_w:
                    current_line = candidate
                else:
                    if current_line:
                        self._lines.append(current_line)
                    current_line = word
            if current_line:
                self._lines.append(current_line)

    def _setup_geometry(self) -> None:
        """Calcula las dimensiones ideales del panel según el número de líneas visibles (1-3)."""
        screen = self.screen()
        if screen:
            geom = screen.geometry()
            w = int(geom.width() * (self.settings.width_pct / 100.0))
            h = int(self._line_height * self.settings.lines_visible + 28)
            x = geom.x() + int((geom.width() - w) * self.settings.position_x)
            y = geom.y() + int(geom.height() * self.settings.position_y)
            self.setGeometry(x, y, w, h)
        else:
            self.resize(800, int(self._line_height * self.settings.lines_visible + 28))

    def _on_anim_tick(self) -> None:
        """Calcula el avance temporal subpíxel por WPM exacto."""
        now = time.perf_counter()
        dt = now - self._last_tick_time
        self._last_tick_time = now

        if self._is_scrolling and not self._is_paused and len(self._lines) > 0:
            # Velocidad en líneas por segundo:
            # Promedio de 8 palabras por línea en un teleprompter estándar
            words_per_line = 7.5
            lines_per_second = (self.settings.wpm / 60.0) / words_per_line
            pixels_per_second = lines_per_second * self._line_height

            self._scroll_offset_y += pixels_per_second * dt

            # Límite superior: detener al finalizar todo el texto
            total_height = len(self._lines) * self._line_height
            if self._scroll_offset_y > total_height + self.height():
                self._is_scrolling = False
                self._anim_timer.stop()

            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Dibuja el fondo acrílico oscuro y las líneas de texto con resaltado."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Fondo oscuro translúcido con esquinas redondeadas
        alpha = int(self.settings.opacity * 255)
        painter.setBrush(QColor(18, 18, 18, alpha))
        painter.setPen(QColor(255, 255, 255, 30))
        painter.drawRoundedRect(self.rect(), 12, 12)

        # Área de recorte de texto
        margin_x = 24
        margin_y = 14
        content_rect = QRect(margin_x, margin_y, self.width() - margin_x * 2, self.height() - margin_y * 2)

        painter.save()
        painter.setClipRect(content_rect)

        font = QFont("Segoe UI", self.settings.font_size)
        font.setBold(True)
        painter.setFont(font)

        # Línea central de enfoque
        focus_y = content_rect.top() + content_rect.height() // 2

        # Dibujar cada línea visible
        start_y = content_rect.top() + int(self._line_height * 0.5) - int(self._scroll_offset_y)

        for idx, line in enumerate(self._lines):
            line_y = start_y + (idx * self._line_height)

            # Omitir líneas fuera de visión para alto rendimiento
            if line_y + self._line_height < content_rect.top() - 20:
                continue
            if line_y > content_rect.bottom() + 20:
                break

            # Distancia al centro de lectura para atenuar líneas previas/posteriores
            dist_to_focus = abs((line_y + self._line_height // 2) - focus_y)
            focus_factor = max(0.35, 1.0 - (dist_to_focus / max(1, self.height() * 0.9)))

            text_color = QColor(255, 255, 255, int(255 * focus_factor))
            painter.setPen(text_color)

            # Dibujar texto centrado horizontalmente
            line_rect = QRect(content_rect.left(), line_y, content_rect.width(), self._line_height)
            painter.drawText(line_rect, Qt.AlignmentFlag.AlignCenter, line)

        painter.restore()

        # Degradado sutil en los bordes superior e inferior para lectura natural
        gradient_top = QLinearGradient(0, 0, 0, 16)
        gradient_top.setColorAt(0, QColor(18, 18, 18, alpha))
        gradient_top.setColorAt(1, QColor(18, 18, 18, 0))
        painter.fillRect(QRect(0, 0, self.width(), 16), gradient_top)

        gradient_bottom = QLinearGradient(0, self.height() - 16, 0, self.height())
        gradient_bottom.setColorAt(0, QColor(18, 18, 18, 0))
        gradient_bottom.setColorAt(1, QColor(18, 18, 18, alpha))
        painter.fillRect(QRect(0, self.height() - 16, self.width(), 16), gradient_bottom)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Permite mover el teleprompter arrastrando con el botón izquierdo."""
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
        """Permite avanzar o retroceder el texto manualmente con la rueda del ratón."""
        delta = event.angleDelta().y()
        # Mover desplazamiento
        self._scroll_offset_y -= delta * 0.4
        self._scroll_offset_y = max(0.0, self._scroll_offset_y)
        self.update()
        event.accept()
