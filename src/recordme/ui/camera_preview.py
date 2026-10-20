"""Ventana flotante de vista previa de cámara interactiva, arrastrable y excluida de captura."""

import logging

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
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

from recordme.core.render_state import CameraLayout
from recordme.platform_services.factory import get_platform_services
from recordme.utils.geometry import Rect, to_logical_pixels, to_physical_pixels

logger = logging.getLogger(__name__)


class CameraPreviewWidget(QWidget):
    """Burbuja flotante de cámara en pantalla con reposicionamiento y redimensionado en tiempo real."""

    layout_updated = Signal(CameraLayout)

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

        self._drag_start_pos: QPoint | None = None
        self._current_pixmap: QPixmap | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._update_geometry_from_layout()

    def update_capture_region(self, region: Rect) -> None:
        """Actualiza el área grabada para calcular correctamente las coordenadas normalizadas."""
        self.capture_region = region
        self._sync_normalized_position()

    def update_frame(self, frame_bgr: npt.NDArray[np.uint8]) -> None:
        """Recibe un nuevo fotograma BGR de la cámara y actualiza el pixmap."""
        try:
            h, w = frame_bgr.shape[:2]
            # Convertir BGR a RGB para Qt
            qimg = QImage(frame_bgr.data, w, h, w * 3, QImage.Format.Format_BGR888)
            self._current_pixmap = QPixmap.fromImage(qimg.copy())
            self.update()
        except Exception as e:
            logger.debug("Error actualizando frame en CameraPreviewWidget: %s", e)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Excluye la ventana de la grabación para que no aparezca duplicada."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Dibuja la vista previa con la forma y borde configurados."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = self.rect()
        path = QPainterPath()

        if self.layout_config.shape == "circle":
            path.addEllipse(QRect(1, 1, rect.width() - 2, rect.height() - 2))
        elif self.layout_config.shape == "rounded_rect":
            radius = int(min(rect.width(), rect.height()) * 0.15)
            path.addRoundedRect(QRect(1, 1, rect.width() - 2, rect.height() - 2), radius, radius)
        else:
            path.addRect(QRect(1, 1, rect.width() - 2, rect.height() - 2))

        painter.save()
        painter.setClipPath(path)

        if self._current_pixmap is not None and not self._current_pixmap.isNull():
            # Dibujar con efecto cover
            scaled = self._current_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            dx = (scaled.width() - self.width()) // 2
            dy = (scaled.height() - self.height()) // 2
            painter.drawPixmap(-dx, -dy, scaled)
        else:
            # Fondo oscuro con icono o texto indicativo
            painter.fillRect(rect, QColor(30, 30, 30))
            painter.setPen(QColor(180, 180, 180))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Cámara")

        painter.restore()

        # Dibujar borde
        if self.layout_config.border_enabled and self.layout_config.border_width > 0:
            pen = QPen(
                QColor(self.layout_config.border_color),
                self.layout_config.border_width,
                Qt.PenStyle.SolidLine,
            )
            painter.setPen(pen)
            painter.drawPath(path)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Inicia el arrastre de la ventana."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Mueve la ventana y calcula la nueva posición normalizada."""
        if self._drag_start_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            self.move(new_pos)
            self._sync_normalized_position()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finaliza el arrastre."""
        self._drag_start_pos = None

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Permite redimensionar la burbuja con la rueda del ratón."""
        delta = event.angleDelta().y()
        change = 2 if delta > 0 else -2
        new_size_pct = max(10, min(self.layout_config.size_pct + change, 45))

        if new_size_pct != self.layout_config.size_pct:
            # Recrear CameraLayout inmutable con el nuevo tamaño
            self.layout_config = CameraLayout(
                enabled=self.layout_config.enabled,
                shape=self.layout_config.shape,
                center_norm_x=self.layout_config.center_norm_x,
                center_norm_y=self.layout_config.center_norm_y,
                size_pct=new_size_pct,
                mirror=self.layout_config.mirror,
                border_enabled=self.layout_config.border_enabled,
                border_width=self.layout_config.border_width,
                border_color=self.layout_config.border_color,
                name_enabled=self.layout_config.name_enabled,
                name_text=self.layout_config.name_text,
                name_position=self.layout_config.name_position,
            )
            self._update_geometry_from_layout()
            self._sync_normalized_position()
            event.accept()

    def _update_geometry_from_layout(self) -> None:
        """Ajusta el tamaño y posición de la ventana según el layout y la región grabada."""
        # Suponiendo DPI actual
        screen = self.screen()
        dpr = screen.devicePixelRatio() if screen else 1.0

        # Ancho físico de salida aproximado
        phys_w = self.capture_region.width
        size_pct = self.layout_config.size_pct / 100.0
        phys_bubble_w = int(phys_w * size_pct)
        phys_bubble_h = phys_bubble_w if self.layout_config.shape in ("circle", "rounded_rect") else int(phys_bubble_w * 9 / 16)

        log_w = max(60, to_logical_pixels(phys_bubble_w, dpr))
        log_h = max(60, to_logical_pixels(phys_bubble_h, dpr))

        self.resize(log_w, log_h)

        # Ubicar según posición normalizada
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

        self.layout_config = CameraLayout(
            enabled=self.layout_config.enabled,
            shape=self.layout_config.shape,
            center_norm_x=float(norm_x),
            center_norm_y=float(norm_y),
            size_pct=self.layout_config.size_pct,
            mirror=self.layout_config.mirror,
            border_enabled=self.layout_config.border_enabled,
            border_width=self.layout_config.border_width,
            border_color=self.layout_config.border_color,
            name_enabled=self.layout_config.name_enabled,
            name_text=self.layout_config.name_text,
            name_position=self.layout_config.name_position,
        )
        self.layout_updated.emit(self.layout_config)
