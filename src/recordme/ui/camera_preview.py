"""Ventana flotante de vista previa de cámara interactiva, arrastrable, redimensionable y excluida de captura."""

import logging
from enum import IntFlag, auto
from typing import Any

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from recordme.camera.segmenter import CameraSegmenter
from recordme.core.render_state import CameraLayout
from recordme.platform_services.factory import get_platform_services
from recordme.utils.geometry import Rect, to_logical_pixels, to_physical_pixels

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


class CameraPreviewWidget(QWidget):
    """Burbuja flotante de cámara en pantalla con redimensionamiento de bordes y arrastre libre."""

    layout_updated = Signal(CameraLayout)
    close_requested = Signal()

    BORDER_GRAB = 8
    MIN_SIZE = 80

    def __init__(
        self,
        initial_layout: CameraLayout,
        capture_region: Rect,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.layout_config = initial_layout
        self.capture_region = capture_region
        self.platform_services = get_platform_services()

        self._active_edge = BoxEdge.NONE
        self._drag_start_pos: QPoint | None = None
        self._drag_start_geom: QRect | None = None
        self._current_pixmap: QPixmap | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        self._update_geometry_from_layout()

    def update_capture_region(self, region: Rect) -> None:
        """Actualiza el área grabada para calcular correctamente las coordenadas normalizadas."""
        self.capture_region = region
        self._sync_normalized_position()

    def update_frame(self, frame_bgr: npt.NDArray[np.uint8]) -> None:
        """Recibe un nuevo fotograma BGR de la cámara, aplica fondo virtual si existe y actualiza el pixmap."""
        try:
            if not self.isVisible() or frame_bgr is None or frame_bgr.size == 0:
                return
            processed_frame = frame_bgr
            if self.layout_config.virtual_bg_image:
                processed_frame = CameraSegmenter.get_instance().apply_background(
                    frame_bgr, self.layout_config.virtual_bg_image
                )
            h, w = processed_frame.shape[:2]
            if not processed_frame.flags["C_CONTIGUOUS"]:
                processed_frame = np.ascontiguousarray(processed_frame)
            bytes_per_line = int(processed_frame.strides[0]) if processed_frame.ndim >= 2 else w * 3
            qimg = QImage(processed_frame.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
            self._current_pixmap = QPixmap.fromImage(qimg.copy())
            self.update()
        except Exception as e:
            logger.debug("Error actualizando frame en CameraPreviewWidget: %s", e)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Excluye la ventana de la grabación para que no aparezca duplicada."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)

    def _determine_edge(self, pos: QPoint) -> BoxEdge:
        """Determina si el cursor está sobre un borde de redimensionamiento o en el interior."""
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

        return BoxEdge.MOVE

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
        """Inicia el arrastre o redimensionado."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._active_edge = self._determine_edge(event.pos())
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_start_geom = self.geometry()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Mueve o redimensiona la ventana."""
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
        self._sync_normalized_position()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finaliza el arrastre."""
        self._drag_start_pos = None
        self._drag_start_geom = None
        self._active_edge = BoxEdge.NONE
        self._sync_normalized_position()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Cierra la vista previa si se presiona la tecla Escape.

        Nota: La tecla 'C' es administrada globalmente por GlobalHotkeyService para evitar
        dobles ejecuciones y condiciones de carrera concurrentes.
        """
        if event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        """Limpia el pixmap al cerrar para liberar memoria de forma segura."""
        self._current_pixmap = None
        super().closeEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Permite redimensionar proporcionalmente con la rueda del ratón."""
        delta = event.angleDelta().y()
        change = 10 if delta > 0 else -10
        new_w = max(self.MIN_SIZE, self.width() + change)
        new_h = max(self.MIN_SIZE, self.height() + int(change * self.height() / max(1, self.width())))
        self.resize(new_w, new_h)
        self._sync_normalized_position()
        event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Dibuja la cámara con su forma (rectángulo o círculo sin bordes) y etiqueta de nombre."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = self.rect()
        path = QPainterPath()

        if self.layout_config.shape == "circle":
            path.addEllipse(QRect(1, 1, rect.width() - 2, rect.height() - 2))
        elif self.layout_config.shape == "rounded_rect":
            radius = int(min(rect.width(), rect.height()) * 0.12)
            path.addRoundedRect(QRect(1, 1, rect.width() - 2, rect.height() - 2), radius, radius)
        else:
            path.addRect(QRect(0, 0, rect.width(), rect.height()))

        painter.save()
        painter.setClipPath(path)

        if self._current_pixmap is not None and not self._current_pixmap.isNull():
            scaled = self._current_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            dx = (scaled.width() - self.width()) // 2
            dy = (scaled.height() - self.height()) // 2
            painter.drawPixmap(-dx, -dy, scaled)
        else:
            painter.fillRect(rect, QColor(30, 30, 30))
            painter.setPen(QColor(180, 180, 180))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Cámara")

        painter.restore()

        # Dibujar borde solo si explícitamente se activa
        if self.layout_config.border_enabled and self.layout_config.border_width > 0:
            pen = QPen(
                QColor(self.layout_config.border_color),
                self.layout_config.border_width,
                Qt.PenStyle.SolidLine,
            )
            painter.setPen(pen)
            painter.drawPath(path)

        # Nombre / Etiqueta del presentador en la parte inferior izquierda
        if self.layout_config.name_enabled and self.layout_config.name_text:
            text = self.layout_config.name_text
            font = QFont("Segoe UI", 9, QFont.Weight.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            t_w = fm.horizontalAdvance(text) + 16
            t_h = fm.height() + 8
            # Ubicar pegado al borde inferior izquierdo sin margen inferior
            badge_rect = QRect(0, self.height() - t_h, min(t_w, self.width()), t_h)

            painter.save()
            # Fondo traslúcido con borde suave estilo frosted glass
            painter.setBrush(QColor(15, 15, 15, 210))
            painter.setPen(QColor(255, 255, 255, 60))
            painter.drawRoundedRect(badge_rect, 5, 5)
            # Texto blanco puro
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
            painter.restore()

    def _update_geometry_from_layout(self) -> None:
        """Ajusta el tamaño y posición de la ventana según el layout y la región grabada."""
        screen = self.screen()
        dpr = screen.devicePixelRatio() if screen else 1.0

        if self.layout_config.shape == "circle":
            log_w = 200
            log_h = 200
        else:
            log_w = 230
            log_h = 120

        self.resize(log_w, log_h)

        log_reg_x = to_logical_pixels(self.capture_region.x, dpr)
        log_reg_y = to_logical_pixels(self.capture_region.y, dpr)
        log_reg_w = to_logical_pixels(self.capture_region.width, dpr)
        log_reg_h = to_logical_pixels(self.capture_region.height, dpr)

        center_x = log_reg_x + int(self.layout_config.center_norm_x * log_reg_w)
        center_y = log_reg_y + int(self.layout_config.center_norm_y * log_reg_h)

        self.move(center_x - log_w // 2, center_y - log_h // 2)

    def _sync_normalized_position(self) -> None:
        """Calcula la posición normalizada (0.0 a 1.0) relativa a la región grabada y emite señal."""
        screen = self.screen()
        dpr = screen.devicePixelRatio() if screen else 1.0

        center_x_log = self.x() + self.width() // 2
        center_y_log = self.y() + self.height() // 2

        center_x_phys = to_physical_pixels(center_x_log, dpr)
        center_y_phys = to_physical_pixels(center_y_log, dpr)

        reg_x = self.capture_region.x
        reg_y = self.capture_region.y
        reg_w = max(1, self.capture_region.width)
        reg_h = max(1, self.capture_region.height)

        norm_x = max(0.05, min((center_x_phys - reg_x) / reg_w, 0.95))
        norm_y = max(0.05, min((center_y_phys - reg_y) / reg_h, 0.95))

        size_pct = int(max(10, min((to_physical_pixels(self.width(), dpr) / reg_w) * 100, 50)))

        self.layout_config = CameraLayout(
            enabled=self.layout_config.enabled,
            shape=self.layout_config.shape,
            center_norm_x=float(norm_x),
            center_norm_y=float(norm_y),
            size_pct=size_pct,
            mirror=self.layout_config.mirror,
            border_enabled=self.layout_config.border_enabled,
            border_width=self.layout_config.border_width,
            border_color=self.layout_config.border_color,
            name_enabled=self.layout_config.name_enabled,
            name_text=self.layout_config.name_text,
            name_position=self.layout_config.name_position,
            virtual_bg_image=self.layout_config.virtual_bg_image,
        )
        self.layout_updated.emit(self.layout_config)
