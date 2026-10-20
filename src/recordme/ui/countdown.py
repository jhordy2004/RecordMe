"""Overlay de cuenta regresiva (3, 2, 1) centrado en el área de captura con exclusión de pantalla."""

import logging

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QShowEvent,
)
from PySide6.QtWidgets import QWidget

from recordme.platform_services.factory import get_platform_services

logger = logging.getLogger(__name__)


class CountdownOverlay(QWidget):
    """Muestra un número grande y nítido (3, 2, 1) centrado exactamente en el área de grabación."""

    finished = Signal()
    canceled = Signal()

    BADGE_SIZE = 130

    def __init__(self, target_rect: QRect | None = None, seconds: int = 3, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.platform_services = get_platform_services()
        self._current_count = max(1, seconds)
        self._target_rect = target_rect

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self.BADGE_SIZE, self.BADGE_SIZE)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        self._position_in_target()

    def _position_in_target(self) -> None:
        """Centra la insignia en el área especificada o en la pantalla completa."""
        if self._target_rect and self._target_rect.isValid() and self._target_rect.width() > 10:
            cx = self._target_rect.center().x()
            cy = self._target_rect.center().y()
        else:
            screen = QGuiApplication.primaryScreen()
            if screen:
                geom = screen.geometry()
                cx = geom.center().x()
                cy = geom.center().y()
            else:
                cx, cy = 600, 400

        x = cx - self.BADGE_SIZE // 2
        y = cy - self.BADGE_SIZE // 2
        self.move(QPoint(x, y))

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Aplica exclusión de captura nativa para que la cuenta atrás jamás salga en el video."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)

    def start(self) -> None:
        """Inicia el temporizador de cuenta atrás y muestra la ventana."""
        self.show()
        self._timer.start()
        self.update()

    def _on_tick(self) -> None:
        """Avanza la cuenta regresiva cada segundo."""
        self._current_count -= 1
        if self._current_count <= 0:
            self._timer.stop()
            self.close()
            self.finished.emit()
        else:
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Permite cancelar la cuenta regresiva pulsando la tecla Esc."""
        if event.key() == Qt.Key.Key_Escape:
            logger.info("Cuenta regresiva cancelada con Escape.")
            self._timer.stop()
            self.close()
            self.canceled.emit()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Dibuja la insignia circular oscura y el número grande de cuenta atrás."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = self.rect().adjusted(4, 4, -4, -4)

        # Fondo circular oscuro acrílico
        painter.setBrush(QColor(18, 18, 18, 235))
        pen = QPen(QColor(0, 180, 216), 3)
        painter.setPen(pen)
        painter.drawEllipse(rect)

        # Número grande
        font = QFont("Segoe UI", 48)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self._current_count))
