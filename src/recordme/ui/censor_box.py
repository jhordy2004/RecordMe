"""Widget flotante interactivo e individual de censura: arrastrable, redimensionable y removible."""

import logging
from enum import IntFlag, auto
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QShowEvent,
)
from PySide6.QtWidgets import QWidget

from recordme.platform_services.factory import get_platform_services
from recordme.utils.geometry import Rect, to_physical_pixels

logger = logging.getLogger(__name__)


class BoxEdge(IntFlag):
    """Bordes y esquinas para redimensionamiento del recuadro."""

    NONE = 0
    LEFT = auto()
    RIGHT = auto()
    TOP = auto()
    BOTTOM = auto()
    TOP_LEFT = TOP | LEFT
    TOP_RIGHT = TOP | RIGHT
    BOTTOM_LEFT = BOTTOM | LEFT
    BOTTOM_RIGHT = BOTTOM | RIGHT
    MOVE = auto()


class CensorBoxWidget(QWidget):
    """Recuadro flotante interactivo de censura superpuesto en pantalla y excluido de captura."""

    geometry_changed = Signal(str, Rect, str)  # (box_id, phys_rect, mode)
    box_closed = Signal(str)  # box_id

    BORDER_GRAB = 8
    MIN_SIZE = 60

    def __init__(
        self,
        box_id: str,
        initial_rect: QRect,
        mode: str = "blur",
        dpr: float = 1.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.box_id = box_id
        self.mode = mode  # blur, pixelate, solid
        self._dpr = max(0.5, dpr)
        self.platform_services = get_platform_services()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._active_edge = BoxEdge.NONE
        self._drag_start_pos: QPoint | None = None
        self._drag_start_geom: QRect | None = None

        self._btn_close_rect = QRect(0, 0, 0, 0)
        self._btn_mode_rect = QRect(0, 0, 0, 0)

        self.setGeometry(initial_rect)
        self._update_button_rects()

    def _update_button_rects(self) -> None:
        """Calcula la posición de los botones en la barra superior del recuadro."""
        w = max(self.MIN_SIZE, self.width())
        self._btn_mode_rect = QRect(4, 2, min(90, max(10, w - 30)), 18)
        self._btn_close_rect = QRect(w - 24, 2, 20, 18)

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_button_rects()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Aplica exclusión nativa de captura para que el marco del widget no salga en el video."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)

    def get_physical_region(self) -> Rect:
        """Devuelve las coordenadas físicas de este recuadro."""
        geom = self.geometry()
        return Rect(
            x=to_physical_pixels(geom.x(), self._dpr),
            y=to_physical_pixels(geom.y(), self._dpr),
            width=to_physical_pixels(geom.width(), self._dpr),
            height=to_physical_pixels(geom.height(), self._dpr),
        ).to_even()

    def _determine_edge(self, pos: QPoint) -> BoxEdge:
        """Determina la acción de redimensionamiento o movimiento bajo el cursor."""
        x = pos.x()
        y = pos.y()
        w = self.width()
        h = self.height()
        b = self.BORDER_GRAB

        edge = BoxEdge.NONE
        if x <= b:
            edge |= BoxEdge.LEFT
        elif x >= w - b:
            edge |= BoxEdge.RIGHT

        if y <= b:
            edge |= BoxEdge.TOP
        elif y >= h - b:
            edge |= BoxEdge.BOTTOM

        if edge != BoxEdge.NONE:
            return edge

        # Si está en el cuerpo interior pero no sobre los botones de la barra superior
        if not self._btn_close_rect.contains(pos) and not self._btn_mode_rect.contains(pos):
            return BoxEdge.MOVE

        return BoxEdge.NONE

    def _update_cursor_shape(self, edge: BoxEdge) -> None:
        """Actualiza el cursor visual según la zona activa."""
        if edge in (BoxEdge.TOP_LEFT, BoxEdge.BOTTOM_RIGHT):
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        elif edge in (BoxEdge.TOP_RIGHT, BoxEdge.BOTTOM_LEFT):
            self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
        elif edge in (BoxEdge.LEFT, BoxEdge.RIGHT):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif edge in (BoxEdge.TOP, BoxEdge.BOTTOM):
            self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        elif edge == BoxEdge.MOVE:
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Maneja clics para cerrar, cambiar modo o iniciar arrastre."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()

            # Botón Cerrar
            if self._btn_close_rect.contains(pos):
                logger.info("Caja de censura %s cerrada por usuario.", self.box_id)
                self.close()
                self.box_closed.emit(self.box_id)
                event.accept()
                return

            # Botón Modo (ciclar entre blur -> pixelate -> solid)
            if self._btn_mode_rect.contains(pos):
                modes = ["blur", "pixelate", "solid"]
                idx = (modes.index(self.mode) + 1) % len(modes) if self.mode in modes else 0
                self.mode = modes[idx]
                self.update()
                self.geometry_changed.emit(self.box_id, self.get_physical_region(), self.mode)
                event.accept()
                return

            self._active_edge = self._determine_edge(pos)
            if self._active_edge != BoxEdge.NONE:
                self._drag_start_pos = event.globalPosition().toPoint()
                self._drag_start_geom = self.geometry()
                event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Mueve o redimensiona la caja de censura."""
        if self._drag_start_pos is None or self._drag_start_geom is None or self._active_edge == BoxEdge.NONE:
            edge = self._determine_edge(event.pos())
            self._update_cursor_shape(edge)
            return

        delta = event.globalPosition().toPoint() - self._drag_start_pos
        dx = delta.x()
        dy = delta.y()

        orig = self._drag_start_geom
        new_x = orig.x()
        new_y = orig.y()
        new_w = orig.width()
        new_h = orig.height()

        if self._active_edge == BoxEdge.MOVE:
            new_x += dx
            new_y += dy
        else:
            if BoxEdge.LEFT in self._active_edge:
                proposed_w = orig.width() - dx
                if proposed_w >= self.MIN_SIZE:
                    new_x = orig.x() + dx
                    new_w = proposed_w
            elif BoxEdge.RIGHT in self._active_edge:
                new_w = max(self.MIN_SIZE, orig.width() + dx)

            if BoxEdge.TOP in self._active_edge:
                proposed_h = orig.height() - dy
                if proposed_h >= self.MIN_SIZE:
                    new_y = orig.y() + dy
                    new_h = proposed_h
            elif BoxEdge.BOTTOM in self._active_edge:
                new_h = max(self.MIN_SIZE, orig.height() + dy)

        self.setGeometry(new_x, new_y, new_w, new_h)
        self.geometry_changed.emit(self.box_id, self.get_physical_region(), self.mode)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finaliza el arrastre y confirma las coordenadas."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = None
            self._drag_start_geom = None
            self._active_edge = BoxEdge.NONE
            self.geometry_changed.emit(self.box_id, self.get_physical_region(), self.mode)
            event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Dibuja el recuadro visual de censura con borde, barra superior y botón de cerrar."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Paleta según modo
        if self.mode == "blur":
            accent = QColor(0, 180, 255)
            bg = QColor(0, 80, 140, 140)
            mode_text = "Desenfoque"
        elif self.mode == "pixelate":
            accent = QColor(168, 85, 247)
            bg = QColor(100, 30, 160, 140)
            mode_text = "Pixelado"
        else:
            accent = QColor(255, 75, 75)
            bg = QColor(20, 20, 20, 210)
            mode_text = "Sólido"

        # Fondo translúcido
        painter.setBrush(bg)
        painter.setPen(QPen(accent, 2, Qt.PenStyle.DashLine))
        painter.drawRoundedRect(1, 1, w - 2, h - 2, 6, 6)

        # Barra superior compacta (22px de altura)
        top_bar_rect = QRect(1, 1, w - 2, 22)
        painter.setBrush(QColor(18, 18, 18, 220))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(top_bar_rect, 6, 6)

        # Botón / Etiqueta de Modo a la izquierda
        self._btn_mode_rect = QRect(4, 2, min(90, w - 30), 18)
        painter.setBrush(accent.darker(150))
        painter.drawRoundedRect(self._btn_mode_rect, 3, 3)

        painter.setPen(QColor(255, 255, 255))
        font_mode = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font_mode)
        painter.drawText(self._btn_mode_rect, Qt.AlignmentFlag.AlignCenter, mode_text)

        # Botón Cerrar (✕) a la derecha
        self._btn_close_rect = QRect(w - 24, 2, 20, 18)
        painter.setBrush(QColor(180, 30, 30, 200))
        painter.drawRoundedRect(self._btn_close_rect, 3, 3)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(self._btn_close_rect, Qt.AlignmentFlag.AlignCenter, "✕")

        # Texto centrado en el cuerpo del recuadro
        if h > 50:
            center_rect = QRect(0, 24, w, h - 24)
            painter.setPen(QColor(255, 255, 255, 180))
            font_body = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
            painter.setFont(font_body)
            painter.drawText(center_rect, Qt.AlignmentFlag.AlignCenter, f"✛ {mode_text}\n(Arrastra para mover)")
