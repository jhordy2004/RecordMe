"""Diálogo interactivo de configuración de cámara: forma, dimensiones, nombre, fondo virtual y vista previa en vivo."""

import logging
from typing import Any

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from recordme.camera.camera_source import CameraSource
from recordme.camera.segmenter import CameraSegmenter
from recordme.config.settings import CameraSettings
from recordme.constants import APP_NAME
from recordme.platform_services.factory import get_platform_services
from recordme.resources import get_app_icon
from recordme.utils.i18n import tr

logger = logging.getLogger(__name__)


class _SafeComboBox(QComboBox):
    """QComboBox que ignora pulsaciones de teclas reservadas para atajos globales como C."""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_C:
            event.accept()
            return
        super().keyPressEvent(event)


class _LivePreviewCanvas(QWidget):
    """Lienzo que muestra la cámara en tiempo real con la forma, fondo virtual y nombre seleccionados."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(260, 150)
        self._current_pixmap: QPixmap | None = None
        self._shape: str = "rect"
        self._name_text: str = ""
        self._bg_path: str | None = None

    def update_settings(self, shape: str, name_text: str, bg_path: str | None) -> None:
        """Actualiza los parámetros visuales de la vista previa."""
        self._shape = shape
        self._name_text = name_text
        self._bg_path = bg_path
        self.update()

    def update_frame(self, frame_bgr: npt.NDArray[np.uint8]) -> None:
        """Recibe el fotograma BGR de la cámara, aplica fondo virtual si existe y repinta."""
        try:
            if frame_bgr is None or frame_bgr.size == 0:
                return
            processed = frame_bgr
            if self._bg_path:
                processed = CameraSegmenter.get_instance().apply_background(frame_bgr, self._bg_path)
            h, w = processed.shape[:2]
            if not processed.flags["C_CONTIGUOUS"]:
                processed = np.ascontiguousarray(processed)
            bytes_per_line = int(processed.strides[0]) if processed.ndim >= 2 else w * 3
            qimg = QImage(processed.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
            self._current_pixmap = QPixmap.fromImage(qimg.copy())
            self.update()
        except Exception as e:
            logger.debug("Error en live preview frame: %s", e)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Dibuja la vista previa con máscara de forma y etiqueta de nombre."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = self.rect()
        path = QPainterPath()

        if self._shape == "circle":
            size = min(rect.width(), rect.height()) - 6
            x = (rect.width() - size) // 2
            y = (rect.height() - size) // 2
            path.addEllipse(QRect(x, y, size, size))
        else:
            path.addRect(QRect(1, 1, rect.width() - 2, rect.height() - 2))

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
            painter.fillRect(rect, QColor(35, 35, 35))
            painter.setPen(QColor(160, 160, 160))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, tr("cam_live_preview"))

        painter.restore()

        # Dibujar nombre opcional en el borde inferior
        if self._name_text:
            font = QFont("Segoe UI", 9, QFont.Weight.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            t_w = fm.horizontalAdvance(self._name_text) + 12
            t_h = fm.height() + 6
            badge_rect = QRect(0, self.height() - t_h, min(t_w, self.width()), t_h)

            painter.save()
            painter.setBrush(QColor(15, 15, 15, 220))
            painter.setPen(QColor(255, 255, 255, 70))
            painter.drawRoundedRect(badge_rect, 4, 4)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self._name_text)
            painter.restore()


class CameraSettingsDialog(QDialog):
    """Panel modal de ajustes de cámara con vista previa en vivo y fondo virtual instantáneo."""

    settings_applied = Signal(CameraSettings)
    _new_frame_signal = Signal(object)

    def __init__(
        self,
        current_settings: CameraSettings,
        camera_source: CameraSource | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = current_settings
        self._external_source = camera_source
        self._local_source: CameraSource | None = None
        self._bg_image_path: str | None = current_settings.background.image if current_settings.background.mode == "image" else None

        self.setWindowTitle(f"{tr('cam_title')} — {APP_NAME}")
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(440)

        self._init_ui()
        self._setup_camera_feed()

    def _init_ui(self) -> None:
        """Construye los controles de forma, dimensiones, nombre, fondo virtual y vista previa."""
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Título
        title_label = QLabel(tr("cam_header"))
        title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #FFFFFF;")
        layout.addWidget(title_label)

        # Vista previa en vivo centrada
        preview_container = QHBoxLayout()
        preview_container.addStretch()
        self.preview_canvas = _LivePreviewCanvas(self)
        self._new_frame_signal.connect(self.preview_canvas.update_frame)
        preview_container.addWidget(self.preview_canvas)
        preview_container.addStretch()
        layout.addLayout(preview_container)

        form = QFormLayout()
        form.setSpacing(10)

        # 1. Forma
        self.combo_shape = _SafeComboBox()
        self.combo_shape.addItem(tr("cam_shape_rect"), "rect")
        self.combo_shape.addItem(tr("cam_shape_circle"), "circle")
        if self.settings.shape == "circle":
            self.combo_shape.setCurrentIndex(1)
        else:
            self.combo_shape.setCurrentIndex(0)
        self.combo_shape.currentIndexChanged.connect(self._sync_preview_params)
        form.addRow(tr("cam_shape"), self.combo_shape)

        # 2. Dimensiones en píxeles: por defecto 230 ancho x 120 altura
        dim_layout = QHBoxLayout()
        self.spin_width = QSpinBox()
        self.spin_width.setRange(80, 1920)
        self.spin_width.setValue(230)
        self.spin_width.setSuffix(" px")

        self.spin_height = QSpinBox()
        self.spin_height.setRange(60, 1080)
        self.spin_height.setValue(120)
        self.spin_height.setSuffix(" px")

        dim_layout.addWidget(QLabel(tr("cam_width")))
        dim_layout.addWidget(self.spin_width)
        dim_layout.addWidget(QLabel(tr("cam_height")))
        dim_layout.addWidget(self.spin_height)
        form.addRow(tr("cam_size"), dim_layout)

        # 3. Nombre del presentador (opcional)
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText(tr("cam_name_placeholder"))
        if self.settings.name.text:
            self.edit_name.setText(self.settings.name.text)
        self.edit_name.textChanged.connect(self._sync_preview_params)
        form.addRow(tr("cam_name_label"), self.edit_name)

        layout.addLayout(form)

        # 4. Fondo Virtual (Zoom-style)
        bg_layout = QHBoxLayout()
        self.btn_browse_bg = QPushButton(tr("cam_browse_bg"))
        self.btn_browse_bg.setStyleSheet(
            "background-color: #2D3748; color: #FFFFFF; font-weight: bold; padding: 6px 12px; border-radius: 4px;"
        )
        self.btn_browse_bg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse_bg.clicked.connect(self._browse_bg_image)

        self.btn_remove_bg = QPushButton(tr("cam_remove_bg"))
        self.btn_remove_bg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_bg.setStyleSheet(
            "background-color: #4A5568; color: #E2E8F0; padding: 6px 10px; border-radius: 4px;"
        )
        self.btn_remove_bg.clicked.connect(self._remove_bg_image)
        self.btn_remove_bg.setVisible(bool(self._bg_image_path))

        bg_layout.addWidget(self.btn_browse_bg)
        bg_layout.addWidget(self.btn_remove_bg)
        bg_layout.addStretch()
        layout.addLayout(bg_layout)

        self.lbl_bg_status = QLabel(
            f"Fondo activo: {self._bg_image_path}" if self._bg_image_path else ""
        )
        self.lbl_bg_status.setStyleSheet("color: #A0AEC0; font-size: 11px;")
        layout.addWidget(self.lbl_bg_status)

        # Botones de Aceptar y Cancelar
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton(tr("btn_cancel"))
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_accept = QPushButton(tr("btn_accept"))
        self.btn_accept.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_accept.setStyleSheet(
            "background-color: #007ACC; color: #FFFFFF; font-weight: bold; padding: 6px 16px; border-radius: 4px;"
        )
        self.btn_accept.clicked.connect(self._on_accept)
        btn_layout.addWidget(self.btn_accept)

        layout.addLayout(btn_layout)

        # Proteger combo_shape y el diálogo contra el atajo C para no alternar a circular involuntariamente
        self.combo_shape.installEventFilter(self)
        self.installEventFilter(self)
        self.btn_accept.setFocus()

        self._sync_preview_params()

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        """Filtra y absorbe la tecla 'C' para evitar que modifique los controles o cambie la forma."""
        if event.type() == QEvent.Type.KeyPress:
            if isinstance(event, QKeyEvent) and event.key() == Qt.Key.Key_C:
                # Si el foco está en el campo de texto del nombre, permitir escribir la 'c'
                if hasattr(self, "edit_name") and self.edit_name.hasFocus():
                    return False
                # En cualquier otro control (incluyendo combo_shape) o en el diálogo, bloquear 'c'
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Evita que presionar la tecla C altere la forma seleccionada o cierre el diálogo."""
        if event.key() == Qt.Key.Key_C:
            if hasattr(self, "edit_name") and self.edit_name.hasFocus():
                super().keyPressEvent(event)
                return
            event.accept()
            return
        super().keyPressEvent(event)

    def _setup_camera_feed(self) -> None:
        """Conecta la fuente de cámara existente o inicia una local para la vista previa."""
        source = self._external_source
        if source and source.is_running:
            source.add_on_frame_callback(self._on_incoming_frame)
        else:
            # Iniciar cámara local para previsualización inmediata
            try:
                self._local_source = CameraSource(width=640, height=480, fps=25)
                self._local_source.add_on_frame_callback(self._on_incoming_frame)
                self._local_source.start()
            except Exception as e:
                logger.debug("No se pudo iniciar cámara local en diálogo: %s", e)

    def _on_incoming_frame(self, frame: npt.NDArray[np.uint8]) -> None:
        """Reenvía el frame al hilo de UI mediante señal Qt de forma segura."""
        try:
            self._new_frame_signal.emit(frame.copy())
        except Exception:
            pass

    def _sync_preview_params(self) -> None:
        """Actualiza los parámetros visuales en el lienzo de previsualización."""
        shape = str(self.combo_shape.currentData())
        name = self.edit_name.text().strip()
        self.preview_canvas.update_settings(shape, name, self._bg_image_path)
        if self._bg_image_path:
            self.lbl_bg_status.setText(f"Fondo activo: {self._bg_image_path}")
            self.btn_remove_bg.setVisible(True)
        else:
            self.lbl_bg_status.setText("")
            self.btn_remove_bg.setVisible(False)

    def _browse_bg_image(self) -> None:
        """Abre el explorador de archivos para elegir una imagen de fondo virtual."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("cam_select_bg_dialog"),
            "",
            tr("cam_image_filter"),
        )
        if file_path:
            self._bg_image_path = file_path
            self._sync_preview_params()

    def _remove_bg_image(self) -> None:
        """Elimina el fondo virtual seleccionado."""
        self._bg_image_path = None
        self._sync_preview_params()

    def _on_accept(self) -> None:
        """Aplica la configuración y cierra el diálogo."""
        selected_shape = str(self.combo_shape.currentData())
        name_text = self.edit_name.text().strip()

        self.settings.shape = selected_shape
        self.settings.border.enabled = False
        self.settings.name.enabled = bool(name_text)
        self.settings.name.text = name_text
        self.settings.name.position = "bottom_left"

        if self._bg_image_path:
            self.settings.background.mode = "image"
            self.settings.background.image = self._bg_image_path
        else:
            self.settings.background.mode = "none"
            self.settings.background.image = None

        self.settings_applied.emit(self.settings)
        self.accept()

    def _cleanup_camera(self) -> None:
        """Limpia los callbacks y detiene la cámara local inmediatamente."""
        if self._external_source:
            try:
                self._external_source.remove_on_frame_callback(self._on_incoming_frame)
            except Exception:
                pass
        if self._local_source:
            try:
                self._local_source.remove_on_frame_callback(self._on_incoming_frame)
                self._local_source.stop()
            except Exception:
                pass
            self._local_source = None

    def showEvent(self, event: Any) -> None:  # noqa: N802
        """Excluye el diálogo de configuración de la captura de pantalla para que no se grabe."""
        super().showEvent(event)
        try:
            get_platform_services().exclude_window_from_capture(self)
        except Exception as e:
            logger.debug("No se pudo excluir CameraSettingsDialog de la captura: %s", e)

    def done(self, r: int) -> None:
        """Asegura la liberación inmediata del hardware de cámara antes de cerrar el diálogo."""
        self._cleanup_camera()
        super().done(r)

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        """Limpia los callbacks y detiene la cámara local al cerrar."""
        self._cleanup_camera()
        super().closeEvent(event)
