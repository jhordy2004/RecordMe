"""Marco visual interactivo para la región de captura seleccionada con controles de redimensionado."""

import logging
from enum import IntFlag, auto
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QCursor,
    QFont,
    QHideEvent,
    QKeyEvent,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QRegion,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import QWidget

from recordme.platform_services.factory import get_platform_services
from recordme.utils.geometry import Rect, to_logical_pixels, to_physical_pixels
from recordme.utils.i18n import tr

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


class RegionCloseButton(QWidget):
    """Botón flotante '✕' situado fuera del área de captura para eliminar el área definida."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.platform_services = get_platform_services()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("btn_delete_region"))
        self._is_hovered = False

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)

    def enterEvent(self, event: Any) -> None:  # noqa: N802
        self._is_hovered = True
        self.update()

    def leaveEvent(self, event: Any) -> None:  # noqa: N802
        self._is_hovered = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fondo circular: rojo al hacer hover, gris oscuro translúcido normalmente
        bg_color = QColor(229, 9, 20) if self._is_hovered else QColor(25, 25, 25, 225)
        border_color = QColor(255, 255, 255, 200) if self._is_hovered else QColor(80, 80, 80, 220)

        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 1.5))
        painter.drawEllipse(1, 1, 23, 23)

        # Letra '✕' centrada
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI", 10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "✕")

    def update_position(self, frame_geom: QRect) -> None:
        """Posiciona el botón fuera del área: justo encima de la esquina superior derecha."""
        btn_w = self.width()
        btn_h = self.height()

        x = frame_geom.right() - btn_w + 1
        y = frame_geom.top() - btn_h - 4

        # Si se sale por la parte superior de la pantalla, colocarlo justo debajo del marco
        if y < 0:
            y = frame_geom.bottom() + 4

        self.move(x, y)


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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self._dpr: float = 1.0
        self._active_edge: ResizeEdge = ResizeEdge.NONE
        self._drag_start_pos: QPoint | None = None
        self._drag_start_geom: QRect | None = None
        self._is_recording = False
        self._is_locked = False
        self._move_handle_rect: QRect = QRect()
        self._is_move_hovered: bool = False

        # Botón '✕' situado afuera del área para eliminar el área definida
        self._close_btn = RegionCloseButton()
        self._close_btn.clicked.connect(self._on_close_clicked)

    def _on_close_clicked(self) -> None:
        """Elimina el área definida y solicita restablecer a pantalla completa."""
        logger.info("El usuario solicitó eliminar el área y restablecer a pantalla completa.")
        self.reset_fullscreen_requested.emit()
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Cancela y restablece a pantalla completa si el usuario presiona Esc fuera de grabación."""
        if event.key() == Qt.Key.Key_Escape and not self._is_recording:
            logger.info("Tecla Esc presionada en el marco: eliminando selección de área.")
            self._on_close_clicked()
            event.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Aplica exclusión de captura nativa para que el marco nunca se grabe en el video."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)
        if not self._is_locked:
            self._close_btn.show()
            self._close_btn.update_position(self.geometry())

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        super().hideEvent(event)
        self._close_btn.hide()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._close_btn.close()
        super().closeEvent(event)

    def moveEvent(self, event: QMoveEvent) -> None:  # noqa: N802
        super().moveEvent(event)
        self._close_btn.update_position(self.geometry())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        """Reconstruye la máscara cuando cambia el tamaño del marco."""
        super().resizeEvent(event)
        self._update_mask_and_layout()

    def set_recording_state(self, recording: bool) -> None:
        """Bloquea el redimensionado y oculta el botón de eliminar área durante la grabación."""
        self._is_recording = recording
        self._is_locked = recording
        self._close_btn.setVisible(not recording and self.isVisible())
        self.update()

    def set_physical_region(self, rect: Rect, dpr: float) -> None:
        """Posiciona y ajusta las dimensiones del marco a partir de coordenadas físicas."""
        self._dpr = dpr if dpr > 0 else 1.0
        log_x = to_logical_pixels(rect.x, self._dpr)
        log_y = to_logical_pixels(rect.y, self._dpr)
        log_w = max(self.MIN_SIZE, to_logical_pixels(rect.width, self._dpr))
        log_h = max(self.MIN_SIZE, to_logical_pixels(rect.height, self._dpr))

        self.setGeometry(log_x, log_y, log_w, log_h)
        self._update_mask_and_layout()
        if self.isVisible() and not self._is_locked:
            self._close_btn.show()
            self._close_btn.update_position(self.geometry())

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
        """Actualiza la máscara del widget para que el interior sea completamente pasante para clics."""
        w = self.width()
        h = self.height()
        b = self.BORDER_THICKNESS

        # Máscara solo sobre los bordes perimetrales: el interior queda 100% pasante
        mask = QRegion()
        mask = mask.united(QRegion(0, 0, w, b))
        mask = mask.united(QRegion(0, h - b, w, b))
        mask = mask.united(QRegion(0, 0, b, h))
        mask = mask.united(QRegion(w - b, 0, b, h))

        # Añadir agarrador de movimiento en la parte superior si no está en grabación
        if not self._is_locked:
            handle_w = min(110, max(70, w - 60))
            handle_h = 24
            self._move_handle_rect = QRect((w - handle_w) // 2, 0, handle_w, handle_h)
            mask = mask.united(QRegion(self._move_handle_rect))
        else:
            self._move_handle_rect = QRect()

        self.setMask(mask)
        self._close_btn.update_position(self.geometry())

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Dibuja únicamente el borde perimetral y los marcadores de esquinas sin tapar el interior."""
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
            painter.drawRect(0, 0, corner_size, corner_size)
            painter.drawRect(w - corner_size, 0, corner_size, corner_size)
            painter.drawRect(0, h - corner_size, corner_size, corner_size)
            painter.drawRect(w - corner_size, h - corner_size, corner_size, corner_size)

            # 3. Píldora / Agarrador para mover el área seleccionada
            if self._move_handle_rect.isValid() and w >= 130:
                hr = self._move_handle_rect.adjusted(0, 1, 0, -1)
                is_active = self._is_move_hovered or self._active_edge == ResizeEdge.MOVE
                bg_color = QColor(0, 180, 216, 240) if is_active else QColor(20, 20, 20, 230)
                border_color = QColor(0, 210, 255) if is_active else QColor(0, 180, 216, 180)

                painter.setBrush(bg_color)
                painter.setPen(QPen(border_color, 1.2))
                painter.drawRoundedRect(hr, 5, 5)

                painter.setPen(QColor(255, 255, 255))
                font = QFont("Segoe UI", 9)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(hr, Qt.AlignmentFlag.AlignCenter, f"✥ {tr('region_frame_move')}")

    def _determine_edge(self, pos: QPoint) -> ResizeEdge:
        """Determina qué borde o esquina está bajo el cursor."""
        if self._is_locked:
            return ResizeEdge.NONE

        # Si el cursor está sobre la píldora de mover
        if self._move_handle_rect.isValid() and self._move_handle_rect.contains(pos):
            return ResizeEdge.MOVE

        x = pos.x()
        y = pos.y()
        w = self.width()
        h = self.height()
        b = self.BORDER_THICKNESS

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
            self._active_edge = self._determine_edge(pos)
            if self._active_edge != ResizeEdge.NONE:
                self._drag_start_pos = event.globalPosition().toPoint()
                self._drag_start_geom = self.geometry()
                event.accept()

    def leaveEvent(self, event: Any) -> None:  # noqa: N802
        super().leaveEvent(event)
        if self._is_move_hovered:
            self._is_move_hovered = False
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Actualiza la forma del cursor o redimensiona/mueve el marco."""
        if self._drag_start_pos is None or self._drag_start_geom is None or self._active_edge == ResizeEdge.NONE:
            pos = event.pos()
            edge = self._determine_edge(pos)
            self._update_cursor_shape(edge)
            was_hovered = self._is_move_hovered
            self._is_move_hovered = (self._move_handle_rect.isValid() and self._move_handle_rect.contains(pos))
            if was_hovered != self._is_move_hovered:
                self.update()
            return

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
        self._close_btn.update_position(self.geometry())
        self.region_changed.emit(self.get_physical_region())
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finaliza el arrastre y emite la región física final confirmada."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = None
            self._drag_start_geom = None
            self._active_edge = ResizeEdge.NONE
            self._close_btn.update_position(self.geometry())
            self.region_changed.emit(self.get_physical_region())
            event.accept()
