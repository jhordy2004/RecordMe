"""Overlay selector de región en pantalla con soporte DPI y exclusión de captura."""

import logging
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QCursor,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from recordme.platform_services.factory import get_platform_services
from recordme.utils.geometry import Rect, to_physical_pixels
from recordme.utils.i18n import tr

logger = logging.getLogger(__name__)


class RegionSelectorOverlay(QWidget):
    """Overlay a pantalla completa para que el usuario seleccione la región a grabar."""

    region_selected = Signal(Rect)  # Emite el Rect en coordenadas físicas pares
    selection_canceled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.platform_services = get_platform_services()

        # Configuración de ventana de overlay translúcido
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

        self._start_pos: QPoint | None = None
        self._current_pos: QPoint | None = None
        self._is_drawing = False
        self._confirmed = False

        # Cubrir la pantalla primaria
        primary_screen = QGuiApplication.primaryScreen()
        if primary_screen:
            geom = primary_screen.geometry()
            self.setGeometry(geom)
            self._dpr = primary_screen.devicePixelRatio()
        else:
            self._dpr = 1.0

    def showEvent(self, event: Any) -> None:  # noqa: N802
        """Aplica exclusión de captura inmediatamente al mostrar el selector."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Dibuja el fondo oscuro semitransparente y el recorte del área seleccionada."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fondo semitransparente
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        selection_rect = self._get_current_rect()
        if selection_rect and selection_rect.isValid() and selection_rect.width() > 4 and selection_rect.height() > 4:
            # Borrar / hacer transparente el área seleccionada
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(selection_rect, Qt.GlobalColor.transparent)

            # Volver a modo normal para el borde y texto
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # Borde azul vibrante
            pen = QPen(QColor(0, 150, 255), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(selection_rect)

            # Información de resolución
            phys_w = to_physical_pixels(selection_rect.width(), self._dpr)
            phys_h = to_physical_pixels(selection_rect.height(), self._dpr)
            info_text = tr("region_selector_dimensions", w=phys_w, h=phys_h)

            # Fondo dinámico para el cartelito según la longitud del texto
            font_metrics = painter.fontMetrics()
            text_w = max(240, font_metrics.horizontalAdvance(info_text) + 24)
            text_rect = QRect(selection_rect.left(), max(0, selection_rect.top() - 28), text_w, 24)
            painter.fillRect(text_rect, QColor(20, 20, 20, 220))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, info_text)
        else:
            # Mensaje de ayuda inicial
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                tr("region_selector_guide"),
            )

    def _get_current_rect(self) -> QRect | None:
        """Devuelve el QRect normalizado según las posiciones de inicio y actual."""
        if self._start_pos is None or self._current_pos is None:
            return None
        return QRect(self._start_pos, self._current_pos).normalized()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Inicia el trazado con clic izquierdo o cancela la selección con clic derecho."""
        if event.button() == Qt.MouseButton.RightButton:
            logger.info("Selección de área cancelada por clic derecho.")
            self.close()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.pos()
            self._current_pos = event.pos()
            self._is_drawing = True
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Actualiza el rectángulo mientras se arrastra."""
        if self._is_drawing:
            self._current_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finaliza el trazado del rectángulo y confirma automáticamente si el área es válida."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_drawing:
            self._is_drawing = False
            self._current_pos = event.pos()
            selected = self._get_current_rect()
            if selected and selected.width() >= 20 and selected.height() >= 20:
                self._confirm_rect(selected)
                return
            self.update()

    def _confirm_rect(self, selected: QRect | None) -> None:
        """Calcula el Rect en píxeles físicos pares, emite la señal y cierra el overlay."""
        self._confirmed = True
        if selected is None or selected.width() < 10 or selected.height() < 10:
            # Pantalla completa por defecto si no dibujó nada
            primary_screen = QGuiApplication.primaryScreen()
            if primary_screen:
                geom = primary_screen.geometry()
                phys_rect = Rect(
                    x=to_physical_pixels(geom.x(), self._dpr),
                    y=to_physical_pixels(geom.y(), self._dpr),
                    width=to_physical_pixels(geom.width(), self._dpr),
                    height=to_physical_pixels(geom.height(), self._dpr),
                ).to_even()
            else:
                phys_rect = Rect(0, 0, 1920, 1080)
        else:
            phys_rect = Rect(
                x=to_physical_pixels(selected.x(), self._dpr),
                y=to_physical_pixels(selected.y(), self._dpr),
                width=to_physical_pixels(selected.width(), self._dpr),
                height=to_physical_pixels(selected.height(), self._dpr),
            ).to_even()

        logger.info("Región confirmada en píxeles físicos: %s", phys_rect)
        self.region_selected.emit(phys_rect)
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Maneja atajos de teclado Enter (confirmar) y Esc (cancelar)."""
        if event.key() == Qt.Key.Key_Escape:
            logger.info("Selección de área cancelada por el usuario.")
            self.close()
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm_rect(self._get_current_rect())
            event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Garantiza la emisión de cancelación y limpieza si no fue confirmada."""
        if not self._confirmed:
            self.selection_canceled.emit()
        super().closeEvent(event)
