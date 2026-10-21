"""Overlay de zoom en vivo a pantalla completa para el escritorio de Windows y todas las aplicaciones."""

import ctypes
import logging
import sys

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPaintEvent,
    QPixmap,
    QShowEvent,
)
from PySide6.QtWidgets import QWidget

from recordme.platform_services.factory import get_platform_services

logger = logging.getLogger(__name__)


class ScreenZoomOverlay(QWidget):
    """Overlay a pantalla completa que magnifica visualmente todo el escritorio en tiempo real."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.platform_services = get_platform_services()

        self._zoom_level: float = 1.0
        self._cx: float = 0.5
        self._cy: float = 0.5

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        primary_screen = QGuiApplication.primaryScreen()
        if primary_screen:
            self.setGeometry(primary_screen.geometry())
        self.hide()

        # Temporizador de refresco solo activo mientras el zoom sea > 100%
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(33)  # ~30 FPS
        self._refresh_timer.timeout.connect(self._on_refresh_tick)

        self._current_pixmap: QPixmap | None = None

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Aplica exclusión de captura y transparencia para clics del ratón a nivel de Windows."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)

        # Hacer completamente traspasable a clics en Windows
        if sys.platform == "win32":
            try:
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                # GWL_EXSTYLE = -20, WS_EX_TRANSPARENT = 0x20, WS_EX_LAYERED = 0x80000
                style = user32.GetWindowLongW(hwnd, -20)
                user32.SetWindowLongW(hwnd, -20, style | 0x20 | 0x80000)
            except Exception as e:
                logger.debug("Error aplicando WS_EX_TRANSPARENT: %s", e)

    def set_zoom(self, zoom: float, cx: float = 0.5, cy: float = 0.5) -> None:
        """Actualiza el nivel de zoom y centro de visualización."""
        self._zoom_level = max(1.0, zoom)
        self._cx = max(0.0, min(1.0, cx))
        self._cy = max(0.0, min(1.0, cy))

        if self._zoom_level <= 1.01:
            self._refresh_timer.stop()
            self._current_pixmap = None
            self.hide()
            logger.info("ScreenZoomOverlay desactivado (100%%).")
        else:
            if not self.isVisible():
                self.show()
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
            self._on_refresh_tick()
            logger.info("ScreenZoomOverlay activo: %.0f%% en (%.2f, %.2f)", self._zoom_level * 100, self._cx, self._cy)

    def _on_refresh_tick(self) -> None:
        """Captura el escritorio subyacente y fuerza el repintado ampliado."""
        if self._zoom_level <= 1.01:
            return

        screen = QGuiApplication.primaryScreen()
        if screen:
            # Captura de pantalla nativa (excluye esta ventana gracias a WDA_EXCLUDEFROMCAPTURE)
            self._current_pixmap = screen.grabWindow(0)
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Pinta el escritorio con zoom ampliado centrado en (cx, cy)."""
        if self._current_pixmap is None or self._current_pixmap.isNull() or self._zoom_level <= 1.01:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = self.width()
        h = self.height()

        crop_w = int(w / self._zoom_level)
        crop_h = int(h / self._zoom_level)

        center_x = int(self._cx * w)
        center_y = int(self._cy * h)

        x1 = max(0, min(center_x - crop_w // 2, w - crop_w))
        y1 = max(0, min(center_y - crop_h // 2, h - crop_h))

        # Recortar y escalar al tamaño completo de la pantalla
        source_rect = QRect(x1, y1, crop_w, crop_h)
        target_rect = QRect(0, 0, w, h)
        painter.drawPixmap(target_rect, self._current_pixmap, source_rect)

        # Indicador HUD discreto arriba al centro
        pct = int(round(self._zoom_level * 100))
        hud_text = f"🔍 Zoom: {pct}%  |  Ctrl+Flechas para mover  |  Ctrl+0 para 100%"
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        hud_w = fm.horizontalAdvance(hud_text) + 24
        hud_h = fm.height() + 10
        hud_rect = QRect((w - hud_w) // 2, 20, hud_w, hud_h)

        painter.setBrush(QColor(10, 10, 10, 220))
        painter.setPen(QColor(0, 229, 255, 180))
        painter.drawRoundedRect(hud_rect, 6, 6)

        painter.setPen(QColor(255, 255, 255))
        painter.drawText(hud_rect, Qt.AlignmentFlag.AlignCenter, hud_text)
