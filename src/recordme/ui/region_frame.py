"""Marco visual interactivo para la región de captura seleccionada con controles de redimensionado."""

import logging
from enum import IntFlag, auto
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QRegion,
    QShowEvent,
)
from PySide6.QtWidgets import QWidget

from recordme.platform_services.factory import get_platform_services
from recordme.utils.geometry import Rect, to_logical_pixels, to_physical_pixels

logger = logging.getLogger(__name__)


class ResizeEdge(IntFlag):
    """Bordes y esquinas para detección de redimensionamiento."""

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


class RegionFrameWidget(QWidget):
    """Marco superpuesto que delimita el área de captura con bordes redimensionables."""

    region_changed = Signal(Rect)  # Emite coordenadas físicas pares
    reset_fullscreen_requested = Signal()

    BORDER_THICKNESS = 10  # Ancho de zona sensible al ratón
    MIN_SIZE = 120

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.platform_services = get_platform_services()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._dpr: float = 1.0
        self._active_edge: ResizeEdge = ResizeEdge.NONE
        self._drag_start_pos: QPoint | None = None
        self._drag_start_geom: QRect | None = None
        self._header_rect = QRect(0, 0, 0, 0)
        self._btn_close_rect = QRect(0, 0, 0, 0)
        self._is_recording = False
        self._is_locked = False
        self._show_badge = True

        # Temporizador para ocultar el cartel de dimensiones tras 2 segundos
        self._badge_timer = QTimer(self)
        self._badge_timer.setSingleShot(True)
        self._badge_timer.timeout.connect(self._hide_badge)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Aplica exclusión de captura nativa para que el marco nunca se grabe en el video."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)

    def set_recording_state(self, recording: bool) -> None:
        """Bloquea el redimensionamiento durante la grabación para proteger el flujo FFmpeg."""
        self._is_recording = recording
        self._is_locked = recording
        self.update()

    def _trigger_badge(self) -> None:
        """Muestra el cartel de dimensiones y reinicia el temporizador de 2 segundos."""
        self._show_badge = True
        self._update_mask_and_layout()
        self.update()
        self._badge_timer.start(2000)

    def _hide_badge(self) -> None:
        """Oculta el cartel de dimensiones para dejar el área completamente visible."""
        self._show_badge = False
        self._update_mask_and_layout()
        self.update()

    def set_physical_region(self, rect: Rect, dpr: float) -> None:
        """Posiciona y ajusta las dimensiones del marco a partir de coordenadas físicas."""
        self._dpr = dpr if dpr > 0 else 1.0
        log_x = to_logical_pixels(rect.x, self._dpr)
        log_y = to_logical_pixels(rect.y, self._dpr)
        log_w = max(self.MIN_SIZE, to_logical_pixels(rect.width, self._dpr))
        log_h = max(self.MIN_SIZE, to_logical_pixels(rect.height, self._dpr))

        self.setGeometry(log_x, log_y, log_w, log_h)
        self._trigger_badge()

    def get_physical_region(self) -> Rect:
        """Obtiene la región actual en píxeles físicos pares."""
        geom = self.geometry()
        return Rect(
            x=to_physical_pixels(geom.x(), self._dpr),
            y=to_physical_pixels(geom.y(), self._dpr),
            width=to_physical_pixels(geom.width(), self._dpr),
            height=to_physical_pixels(geom.height(), self._dpr),
        ).to_even()

    def _update_mask_and_layout(self) -> None:
        """Actualiza la máscara del widget para que el interior sea pasante para clics."""
        w = self.width()
        h = self.height()
        b = self.BORDER_THICKNESS

        # Insignia de título superior (dimensiones e icono para pantalla completa)
        header_w = min(220, max(140, w - 40))
        header_h = 24
        header_x = (w - header_w) // 2
        header_y = 0
        self._header_rect = QRect(header_x, header_y, header_w, header_h)
        self._btn_close_rect = QRect(header_x + header_w - 22, header_y + 2, 20, 20)

        # Máscara: bordes siempre, e insignia solo si está visible
        mask = QRegion()
        # Bordes
        mask = mask.united(QRegion(0, 0, w, b))
        mask = mask.united(QRegion(0, h - b, w, b))
        mask = mask.united(QRegion(0, 0, b, h))
        mask = mask.united(QRegion(w - b, 0, b, h))
        # Insignia superior (solo cuando _show_badge está activo)
        if self._show_badge:
            mask = mask.united(QRegion(self._header_rect))

        self.setMask(mask)

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        """Reconstruye la máscara cuando cambia el tamaño del marco."""
        super().resizeEvent(event)
        self._update_mask_and_layout()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Dibuja el borde visible de captura, esquinas de ajuste e insignia superior."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Color: azul cian en modo edición, rojo vibrante durante grabación
        border_color = QColor(229, 9, 20) if self._is_recording else QColor(0, 180, 216)

        # 1. Borde perimetral del área de captura
        pen = QPen(border_color, 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(1, 1, w - 2, h - 2)

        # 2. Marcadores en las 4 esquinas si no está bloqueado
        if not self._is_locked:
            corner_size = 8
            painter.setBrush(border_color)
            painter.setPen(Qt.PenStyle.NoPen)
            # Esquinas
            painter.drawRect(0, 0, corner_size, corner_size)
            painter.drawRect(w - corner_size, 0, corner_size, corner_size)
            painter.drawRect(0, h - corner_size, corner_size, corner_size)
            painter.drawRect(w - corner_size, h - corner_size, corner_size, corner_size)

        # 3. Insignia superior con resolución física (si está activa)
        if self._show_badge:
            phys_rect = self.get_physical_region()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(20, 20, 20, 230))
            painter.drawRoundedRect(self._header_rect, 4, 4)

            # Texto de dimensiones
            font = QFont("Segoe UI", 9)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))

            label_rect = QRect(
                self._header_rect.left() + 6,
                self._header_rect.top(),
                self._header_rect.width() - 28,
                self._header_rect.height(),
            )
            status_text = f"Área: {phys_rect.width}×{phys_rect.height}"
            if self._is_recording:
                status_text += " [REC]"
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, status_text)

            # Botón para volver a pantalla completa (✕)
            if not self._is_locked:
                painter.setPen(QColor(180, 180, 180))
                painter.drawText(self._btn_close_rect, Qt.AlignmentFlag.AlignCenter, "✕")

    def _determine_edge(self, pos: QPoint) -> ResizeEdge:
        """Determina qué borde o esquina está bajo el cursor."""
        if self._is_locked:
            return ResizeEdge.NONE

        x = pos.x()
        y = pos.y()
        w = self.width()
        h = self.height()
        b = self.BORDER_THICKNESS

        # Insignia superior para mover
        if self._show_badge and self._header_rect.contains(pos) and not self._btn_close_rect.contains(pos):
            return ResizeEdge.MOVE

        edge = ResizeEdge.NONE
        if x <= b:
            edge |= ResizeEdge.LEFT
        elif x >= w - b:
            edge |= ResizeEdge.RIGHT

        if y <= b:
            edge |= ResizeEdge.TOP
        elif y >= h - b:
            edge |= ResizeEdge.BOTTOM

        return edge

    def _update_cursor_shape(self, edge: ResizeEdge) -> None:
        """Cambia el cursor según el borde activo."""
        if edge in (ResizeEdge.TOP_LEFT, ResizeEdge.BOTTOM_RIGHT):
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        elif edge in (ResizeEdge.TOP_RIGHT, ResizeEdge.BOTTOM_LEFT):
            self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
        elif edge in (ResizeEdge.LEFT, ResizeEdge.RIGHT):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif edge in (ResizeEdge.TOP, ResizeEdge.BOTTOM):
            self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        elif edge == ResizeEdge.MOVE:
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Inicia el arrastre de redimensionamiento o movimiento del marco."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            # Clic en el botón cerrar del encabezado para volver a pantalla completa
            if self._show_badge and not self._is_locked and self._btn_close_rect.contains(pos):
                logger.info("El usuario solicitó restablecer a pantalla completa.")
                self.reset_fullscreen_requested.emit()
                self.close()
                return

            self._active_edge = self._determine_edge(pos)
            if self._active_edge != ResizeEdge.NONE:
                self._trigger_badge()
                self._drag_start_pos = event.globalPosition().toPoint()
                self._drag_start_geom = self.geometry()
                event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Actualiza la forma del cursor o redimensiona/mueve el marco."""
        if self._drag_start_pos is None or self._drag_start_geom is None or self._active_edge == ResizeEdge.NONE:
            # Solo actualizar cursor en hover
            edge = self._determine_edge(event.pos())
            self._update_cursor_shape(edge)
            return

        self._trigger_badge()
        delta = event.globalPosition().toPoint() - self._drag_start_pos
        dx = delta.x()
        dy = delta.y()

        orig = self._drag_start_geom
        new_x = orig.x()
        new_y = orig.y()
        new_w = orig.width()
        new_h = orig.height()

        if self._active_edge == ResizeEdge.MOVE:
            new_x += dx
            new_y += dy
        else:
            if ResizeEdge.LEFT in self._active_edge:
                proposed_w = orig.width() - dx
                if proposed_w >= self.MIN_SIZE:
                    new_x = orig.x() + dx
                    new_w = proposed_w
            elif ResizeEdge.RIGHT in self._active_edge:
                new_w = max(self.MIN_SIZE, orig.width() + dx)

            if ResizeEdge.TOP in self._active_edge:
                proposed_h = orig.height() - dy
                if proposed_h >= self.MIN_SIZE:
                    new_y = orig.y() + dy
                    new_h = proposed_h
            elif ResizeEdge.BOTTOM in self._active_edge:
                new_h = max(self.MIN_SIZE, orig.height() + dy)

        self.setGeometry(new_x, new_y, new_w, new_h)
        self.region_changed.emit(self.get_physical_region())
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finaliza el arrastre y emite la región física final confirmada."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = None
            self._drag_start_geom = None
            self._active_edge = ResizeEdge.NONE
            self.region_changed.emit(self.get_physical_region())
            event.accept()
