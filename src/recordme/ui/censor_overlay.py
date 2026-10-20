"""Overlay visual para definir, modificar y gestionar regiones de censura en tiempo real."""

import logging
import uuid

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from recordme.core.render_state import CensorRegion
from recordme.platform_services.factory import get_platform_services
from recordme.utils.geometry import Rect, to_logical_pixels, to_physical_pixels

logger = logging.getLogger(__name__)


class CensorOverlay(QWidget):
    """Overlay interactivo para dibujar cajas de censura (desenfoque, pixelado, sólido)."""

    regions_changed = Signal(list)  # Emite list[CensorRegion]

    def __init__(
        self,
        existing_regions: list[CensorRegion] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.platform_services = get_platform_services()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

        primary_screen = QGuiApplication.primaryScreen()
        if primary_screen:
            self.setGeometry(primary_screen.geometry())
            self._dpr = primary_screen.devicePixelRatio()
        else:
            self._dpr = 1.0

        self._regions: list[CensorRegion] = list(existing_regions) if existing_regions else []
        self._start_pos: QPoint | None = None
        self._current_pos: QPoint | None = None
        self._is_drawing = False

        self._current_mode = "blur"  # blur, pixelate, solid
        self._init_top_bar()

    def _init_top_bar(self) -> None:
        """Barra flotante superior de control de censura."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        top_container = QWidget(self)
        top_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        top_container.setStyleSheet(
            """
            QWidget {
                background-color: rgba(24, 24, 24, 240);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
            }
            QLabel {
                color: #FFFFFF;
                font-weight: bold;
                border: none;
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 5px;
                padding: 5px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #444444;
            }
            QComboBox {
                background-color: #2E2E2E;
                color: #FFFFFF;
                border: 1px solid #444444;
                border-radius: 5px;
                padding: 4px 10px;
                font-weight: bold;
            }
            """
        )
        top_bar = QHBoxLayout(top_container)
        top_bar.setContentsMargins(14, 8, 14, 8)
        top_bar.setSpacing(12)

        title = QLabel("Censura en Tiempo Real — Dibuja un rectángulo para ocultar")
        top_bar.addWidget(title)

        top_bar.addSpacing(10)
        mode_label = QLabel("Modo:")
        top_bar.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Desenfoque (Blur)", "blur")
        self.mode_combo.addItem("Pixelado", "pixelate")
        self.mode_combo.addItem("Sólido Negro", "solid")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        top_bar.addWidget(self.mode_combo)

        top_bar.addStretch()

        self.btn_clear = QPushButton("Borrar todas")
        self.btn_clear.clicked.connect(self._clear_all)
        top_bar.addWidget(self.btn_clear)

        self.btn_done = QPushButton("✓ Guardar y Salir (Esc)")
        self.btn_done.setStyleSheet("background-color: #007ACC; color: white;")
        self.btn_done.clicked.connect(self._on_done)
        top_bar.addWidget(self.btn_done)

        main_layout.addWidget(top_container, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        main_layout.addStretch()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Aplica exclusión nativa de captura para que el editor de censura no salga en el video."""
        super().showEvent(event)
        self.platform_services.exclude_window_from_capture(self)

    def _on_mode_changed(self) -> None:
        """Actualiza el modo actual para nuevos rectángulos dibujados."""
        self._current_mode = str(self.mode_combo.currentData())

    def _clear_all(self) -> None:
        """Elimina todas las cajas de censura."""
        self._regions.clear()
        self.regions_changed.emit(self._regions)
        self.update()

    def _on_done(self) -> None:
        """Cierra el overlay y confirma las regiones activas."""
        self.regions_changed.emit(self._regions)
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Permite cerrar y confirmar con Esc o Enter."""
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_done()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Inicia el trazado de una nueva región de censura o eliminación con clic secundario."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.pos()
            self._current_pos = event.pos()
            self._is_drawing = True
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            # Eliminar la región bajo el cursor si existe
            click_phys = QPoint(
                to_physical_pixels(event.pos().x(), self._dpr),
                to_physical_pixels(event.pos().y(), self._dpr),
            )
            self._regions = [
                r for r in self._regions if not r.rect.contains(click_phys.x(), click_phys.y())
            ]
            self.regions_changed.emit(self._regions)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Actualiza el rectángulo en trazado."""
        if self._is_drawing:
            self._current_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Confirma la nueva región de censura si supera el tamaño mínimo."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_drawing:
            self._is_drawing = False
            self._current_pos = event.pos()

            rect_log = self._get_drawing_rect()
            if rect_log and rect_log.width() >= 15 and rect_log.height() >= 15:
                phys_rect = Rect(
                    x=to_physical_pixels(rect_log.x(), self._dpr),
                    y=to_physical_pixels(rect_log.y(), self._dpr),
                    width=to_physical_pixels(rect_log.width(), self._dpr),
                    height=to_physical_pixels(rect_log.height(), self._dpr),
                ).to_even()

                new_region = CensorRegion(
                    id=str(uuid.uuid4())[:8],
                    rect=phys_rect,
                    mode=self._current_mode,
                    active=True,
                )
                self._regions.append(new_region)
                self.regions_changed.emit(self._regions)

            self._start_pos = None
            self._current_pos = None
            self.update()

    def _get_drawing_rect(self) -> QRect | None:
        """Calcula el QRect normalizado del rectángulo que se está dibujando."""
        if self._start_pos is None or self._current_pos is None:
            return None
        return QRect(self._start_pos, self._current_pos).normalized()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Dibuja el fondo translúcido, las regiones existentes y el rectángulo en dibujo."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fondo sutil para enfocar la edición
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

        # 1. Dibujar regiones guardadas
        for reg in self._regions:
            rx = to_logical_pixels(reg.rect.x, self._dpr)
            ry = to_logical_pixels(reg.rect.y, self._dpr)
            rw = to_logical_pixels(reg.rect.width, self._dpr)
            rh = to_logical_pixels(reg.rect.height, self._dpr)
            box = QRect(rx, ry, rw, rh)

            # Relleno visual según modo
            if reg.mode == "blur":
                painter.fillRect(box, QColor(0, 150, 255, 90))
                pen_color = QColor(0, 180, 255)
                mode_str = "Desenfoque"
            elif reg.mode == "pixelate":
                painter.fillRect(box, QColor(140, 20, 252, 90))
                pen_color = QColor(160, 60, 255)
                mode_str = "Pixelado"
            else:
                painter.fillRect(box, QColor(0, 0, 0, 180))
                pen_color = QColor(255, 255, 255)
                mode_str = "Sólido"

            painter.setPen(QPen(pen_color, 2, Qt.PenStyle.DashLine))
            painter.drawRect(box)

            # Etiqueta de la caja
            badge_rect = QRect(box.left(), max(0, box.top() - 20), 90, 18)
            painter.fillRect(badge_rect, QColor(20, 20, 20, 220))
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, mode_str)

        # 2. Dibujar rectángulo que se está trazando actualmente
        drawing_rect = self._get_drawing_rect()
        if drawing_rect and drawing_rect.width() > 4 and drawing_rect.height() > 4:
            painter.fillRect(drawing_rect, QColor(255, 255, 255, 50))
            painter.setPen(QPen(QColor(0, 255, 200), 2, Qt.PenStyle.SolidLine))
            painter.drawRect(drawing_rect)
