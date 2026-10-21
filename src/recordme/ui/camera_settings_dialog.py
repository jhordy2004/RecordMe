"""Diálogo interactivo de configuración de cámara: forma, dimensiones, nombre y fondo virtual."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
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

from recordme.config.settings import CameraSettings
from recordme.constants import APP_NAME

logger = logging.getLogger(__name__)


class CameraSettingsDialog(QDialog):
    """Panel modal de ajustes de cámara previo o durante la grabación."""

    settings_applied = Signal(CameraSettings)

    def __init__(self, current_settings: CameraSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = current_settings
        self.setWindowTitle(f"Configuración de Cámara — {APP_NAME}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(380)
        self._init_ui()

    def _init_ui(self) -> None:
        """Construye los controles de forma, dimensiones, nombre y fondo virtual."""
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        # Título
        title_label = QLabel("Ajustes de Cámara")
        title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #FFFFFF;")
        layout.addWidget(title_label)

        form = QFormLayout()
        form.setSpacing(10)

        # 1. Forma
        self.combo_shape = QComboBox()
        self.combo_shape.addItem("Rectángulo (sin bordes)", "rect")
        self.combo_shape.addItem("Círculo (sin bordes)", "circle")
        if self.settings.shape == "circle":
            self.combo_shape.setCurrentIndex(1)
        else:
            self.combo_shape.setCurrentIndex(0)
        form.addRow("Forma de cámara:", self.combo_shape)

        # 2. Dimensiones en píxeles (ancho x alto)
        dim_layout = QHBoxLayout()
        self.spin_width = QSpinBox()
        self.spin_width.setRange(100, 1920)
        self.spin_width.setValue(320)
        self.spin_width.setSuffix(" px")

        self.spin_height = QSpinBox()
        self.spin_height.setRange(100, 1080)
        self.spin_height.setValue(240)
        self.spin_height.setSuffix(" px")

        dim_layout.addWidget(QLabel("Ancho:"))
        dim_layout.addWidget(self.spin_width)
        dim_layout.addWidget(QLabel("Alto:"))
        dim_layout.addWidget(self.spin_height)
        form.addRow("Tamaño:", dim_layout)

        # 3. Nombre del presentador (opcional)
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Opcional (Ej. Tu nombre)")
        if self.settings.name.text:
            self.edit_name.setText(self.settings.name.text)
        form.addRow("Nombre / Etiqueta:", self.edit_name)

        layout.addLayout(form)

        # 4. Fondo Virtual (estilo Zoom)
        bg_group = QVBoxLayout()
        bg_group.setSpacing(6)

        self.chk_virtual_bg = QCheckBox("Habilitar Fondo Virtual")
        self.chk_virtual_bg.setChecked(self.settings.background.mode == "image")

        bg_path_layout = QHBoxLayout()
        self.edit_bg_path = QLineEdit()
        self.edit_bg_path.setReadOnly(True)
        self.edit_bg_path.setPlaceholderText("Selecciona una imagen de fondo...")
        if self.settings.background.image:
            self.edit_bg_path.setText(str(self.settings.background.image))

        self.btn_browse_bg = QPushButton("Examinar...")
        self.btn_browse_bg.clicked.connect(self._browse_bg_image)

        bg_path_layout.addWidget(self.edit_bg_path)
        bg_path_layout.addWidget(self.btn_browse_bg)

        bg_group.addWidget(self.chk_virtual_bg)
        bg_group.addLayout(bg_path_layout)
        layout.addLayout(bg_group)

        # Botones de Aceptar y Cancelar
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_accept = QPushButton("Aceptar")
        self.btn_accept.setStyleSheet(
            "background-color: #007ACC; color: #FFFFFF; font-weight: bold; padding: 6px 14px; border-radius: 4px;"
        )
        self.btn_accept.clicked.connect(self._on_accept)
        btn_layout.addWidget(self.btn_accept)

        layout.addLayout(btn_layout)

    def _browse_bg_image(self) -> None:
        """Abre el explorador de archivos para elegir una imagen de fondo virtual."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar fondo virtual",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if file_path:
            self.edit_bg_path.setText(file_path)
            self.chk_virtual_bg.setChecked(True)

    def _on_accept(self) -> None:
        """Guarda y emite los ajustes actualizados."""
        selected_shape = self.combo_shape.currentData()
        name_text = self.edit_name.text().strip()

        self.settings.shape = str(selected_shape)
        self.settings.border.enabled = False  # Sin borde
        self.settings.name.enabled = bool(name_text)
        self.settings.name.text = name_text
        self.settings.name.position = "bottom_left"

        if self.chk_virtual_bg.isChecked() and self.edit_bg_path.text().strip():
            self.settings.background.mode = "image"
            self.settings.background.image = self.edit_bg_path.text().strip()
        else:
            self.settings.background.mode = "none"
            self.settings.background.image = None

        self.settings_applied.emit(self.settings)
        self.accept()
