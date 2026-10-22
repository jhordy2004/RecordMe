"""Overlay interactivo para dibujar y definir el área exacta que se desea censurar."""

import logging
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from recordme.platform_services.factory import get_platform_services
from recordme.utils.i18n import tr

logger = logging.getLogger(__name__)


class CensorAreaSelectorOverlay(QWidget):
    """Overlay a pantalla completa para marcar interactivamente el área de censura."""

    area_selected = Signal(QRect)  # Emite el QRect en coordenadas lógicas
    selection_canceled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.platform_services = get_platform_services()

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

        primary_screen = QGuiApplication.primaryScreen()
        if primary_screen:
            self.setGeometry(primary_screen.geometry())
            self._dpr = primary_screen.devicePixelRatio()
        else:
            self._dpr = 1.0

    def showEvent(self, event: Any) -> None:  # noqa: N802
        """Aplica exclusión de captura nativa para no salir grabado."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Inicia el trazado del área de censura o cancela con clic derecho."""
        if event.button() == Qt.MouseButton.RightButton:
            logger.info("Trazado de censura cancelado por clic derecho.")
            self.close()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.pos()
            self._current_pos = event.pos()
            self._is_drawing = True
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Actualiza el rectángulo trazado en tiempo real."""
        if self._is_drawing:
            self._current_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finaliza el trazado y emite el área si tiene un tamaño mínimo."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_drawing:
            self._is_drawing = False
            self._current_pos = event.pos()

            if self._start_pos is not None and self._current_pos is not None:
                selected_rect = QRect(self._start_pos, self._current_pos).normalized()
                # Exigir un tamaño mínimo de 30x30 para evitar clics accidentales
                if selected_rect.width() >= 30 and selected_rect.height() >= 30:
                    logger.info("Área de censura trazada: %s", selected_rect)
                    self._confirmed = True
                    self.close()
                    self.area_selected.emit(selected_rect)
                    return

            self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Cancela con tecla Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Emite cancelación si se cierra la ventana sin haber trazado."""
        if not self._confirmed:
            self.selection_canceled.emit()
        super().closeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Pinta la máscara oscura y resalta el área trazada en color azul cian."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fondo oscuro atenuado
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

        if self._start_pos and self._current_pos:
            rect = QRect(self._start_pos, self._current_pos).normalized()

            # Área seleccionada transparente
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # Borde del área trazada
            pen = QPen(QColor(0, 229, 255), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Dimensiones
            info_text = tr("censor_selector_dimensions", w=rect.width(), h=rect.height())
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.setPen(QColor(0, 229, 255))
            painter.drawText(rect.x() + 6, max(20, rect.y() - 6), info_text)
        else:
            # Mensaje guía
            painter.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
            painter.setPen(QColor(255, 255, 255, 220))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                tr("censor_selector_guide"),
            )
