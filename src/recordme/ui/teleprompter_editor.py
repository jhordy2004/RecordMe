"""Editor de teleprompter: carga de texto, ajuste de velocidad WPM, tamaño y vista previa."""

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from recordme.config.paths import get_scripts_dir
from recordme.config.settings import TeleprompterSettings
from recordme.constants import APP_NAME

logger = logging.getLogger(__name__)


class TeleprompterEditorDialog(QDialog):
    """Diálogo completo de edición y configuración del guion del teleprompter."""

    settings_applied = Signal(str, TeleprompterSettings)
    test_requested = Signal(str, TeleprompterSettings)

    def __init__(
        self,
        current_text: str,
        settings: TeleprompterSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings

        self.setWindowTitle(f"Teleprompter — {APP_NAME}")
        self.resize(720, 560)
        self.setMinimumSize(600, 480)

        self._init_ui(current_text)
        self._update_stats()

    def _init_ui(self, initial_text: str) -> None:
        """Construye los controles y el área de edición."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Barra superior con botones de guion
        top_bar = QHBoxLayout()
        title_label = QLabel("Guion del Teleprompter")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFFFFF;")
        top_bar.addWidget(title_label)
        top_bar.addStretch()

        self.btn_open = QPushButton("Abrir .txt...")
        self.btn_open.clicked.connect(self._open_file)
        top_bar.addWidget(self.btn_open)

        self.btn_save_script = QPushButton("Guardar guion...")
        self.btn_save_script.clicked.connect(self._save_file)
        top_bar.addWidget(self.btn_save_script)

        layout.addLayout(top_bar)

        # Editor de texto grande
        self.text_edit = QTextEdit(self)
        self.text_edit.setPlaceholderText("Pega o escribe aquí el texto que deseas leer durante tu grabación...")
        self.text_edit.setPlainText(initial_text)
        self.text_edit.setStyleSheet(
            """
            QTextEdit {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3A3A3A;
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
                font-family: 'Segoe UI', sans-serif;
            }
            """
        )
        self.text_edit.textChanged.connect(self._update_stats)
        layout.addWidget(self.text_edit, stretch=1)

        # Contador de palabras y tiempo estimado
        self.stats_label = QLabel("0 palabras — Tiempo estimado: 00:00")
        self.stats_label.setStyleSheet("color: #00B4D8; font-weight: bold; font-size: 12px;")
        layout.addWidget(self.stats_label)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Formulario de ajustes interactivos
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 1. Velocidad WPM
        wpm_box = QHBoxLayout()
        self.wpm_slider = QSlider(Qt.Orientation.Horizontal)
        self.wpm_slider.setRange(40, 300)
        self.wpm_slider.setValue(self.settings.wpm)
        self.wpm_spin = QSpinBox()
        self.wpm_spin.setRange(40, 300)
        self.wpm_spin.setValue(self.settings.wpm)
        self.wpm_spin.setSuffix(" WPM")
        self.wpm_slider.valueChanged.connect(self.wpm_spin.setValue)
        self.wpm_spin.valueChanged.connect(self.wpm_slider.setValue)
        self.wpm_spin.valueChanged.connect(self._update_stats)
        wpm_box.addWidget(self.wpm_slider, stretch=1)
        wpm_box.addWidget(self.wpm_spin)
        form_layout.addRow("Velocidad:", wpm_box)

        # 2. Tamaño de fuente
        font_box = QHBoxLayout()
        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(18, 64)
        self.font_slider.setValue(self.settings.font_size)
        self.font_spin = QSpinBox()
        self.font_spin.setRange(18, 64)
        self.font_spin.setValue(self.settings.font_size)
        self.font_spin.setSuffix(" px")
        self.font_slider.valueChanged.connect(self.font_spin.setValue)
        self.font_spin.valueChanged.connect(self.font_slider.setValue)
        font_box.addWidget(self.font_slider, stretch=1)
        font_box.addWidget(self.font_spin)
        form_layout.addRow("Tamaño de letra:", font_box)

        # 3. Líneas visibles
        lines_box = QHBoxLayout()
        self.lines_slider = QSlider(Qt.Orientation.Horizontal)
        self.lines_slider.setRange(1, 3)
        self.lines_slider.setValue(self.settings.lines_visible)
        self.lines_spin = QSpinBox()
        self.lines_spin.setRange(1, 3)
        self.lines_spin.setValue(self.settings.lines_visible)
        self.lines_spin.setSuffix(" líneas")
        self.lines_slider.valueChanged.connect(self.lines_spin.setValue)
        self.lines_spin.valueChanged.connect(self.lines_slider.setValue)
        lines_box.addWidget(self.lines_slider, stretch=1)
        lines_box.addWidget(self.lines_spin)
        form_layout.addRow("Líneas visibles:", lines_box)

        # 4. Opacidad del fondo
        opacity_box = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(int(self.settings.opacity * 100))
        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(30, 100)
        self.opacity_spin.setValue(int(self.settings.opacity * 100))
        self.opacity_spin.setSuffix(" %")
        self.opacity_slider.valueChanged.connect(self.opacity_spin.setValue)
        self.opacity_spin.valueChanged.connect(self.opacity_slider.setValue)
        opacity_box.addWidget(self.opacity_slider, stretch=1)
        opacity_box.addWidget(self.opacity_spin)
        form_layout.addRow("Opacidad del fondo:", opacity_box)

        layout.addLayout(form_layout)

        # Botones inferiores de acción
        btn_layout = QHBoxLayout()
        self.btn_test = QPushButton("Probar Teleprompter")
        self.btn_test.setStyleSheet("background-color: #2E7D32; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 6px;")
        self.btn_test.clicked.connect(self._on_test_clicked)
        btn_layout.addWidget(self.btn_test)

        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_apply = QPushButton("Aplicar y Mostrar")
        self.btn_apply.setStyleSheet("background-color: #007ACC; color: #FFFFFF; font-weight: bold; padding: 8px 20px; border-radius: 6px;")
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)

    def _update_stats(self) -> None:
        """Calcula el número de palabras y el tiempo estimado de lectura."""
        text = self.text_edit.toPlainText().strip()
        words = len(text.split()) if text else 0
        wpm = max(40, self.wpm_spin.value())

        total_seconds = int((words / wpm) * 60)
        mins = total_seconds // 60
        secs = total_seconds % 60
        self.stats_label.setText(f"{words} palabras — Tiempo estimado: {mins:02d}:{secs:02d} (a {wpm} WPM)")

    def _open_file(self) -> None:
        """Abre un diálogo para cargar un archivo de texto .txt."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir guion de texto",
            str(get_scripts_dir()),
            "Archivos de texto (*.txt);;Todos los archivos (*.*)",
        )
        if path:
            try:
                content = Path(path).read_text(encoding="utf-8")
                self.text_edit.setPlainText(content)
            except Exception:
                try:
                    content = Path(path).read_text(encoding="latin-1")
                    self.text_edit.setPlainText(content)
                except Exception as e:
                    logger.error("No se pudo leer el archivo: %s", e)

    def _save_file(self) -> None:
        """Guarda el guion actual como archivo .txt."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar guion de texto",
            str(get_scripts_dir() / "guion.txt"),
            "Archivos de texto (*.txt)",
        )
        if path:
            try:
                Path(path).write_text(self.text_edit.toPlainText(), encoding="utf-8")
            except Exception as e:
                logger.error("Error guardando guion: %s", e)

    def get_current_settings(self) -> TeleprompterSettings:
        """Construye un TeleprompterSettings con los valores actuales del diálogo."""
        return TeleprompterSettings(
            enabled=True,
            font_size=self.font_spin.value(),
            wpm=self.wpm_spin.value(),
            lines_visible=self.lines_spin.value(),
            opacity=self.opacity_spin.value() / 100.0,
            width_pct=self.settings.width_pct,
            position_x=self.settings.position_x,
            position_y=self.settings.position_y,
            last_script=self.text_edit.toPlainText(),
        )

    def _on_test_clicked(self) -> None:
        """Emite la señal de prueba para lanzar la previsualización del teleprompter."""
        text = self.text_edit.toPlainText().strip()
        settings = self.get_current_settings()
        self.test_requested.emit(text, settings)

    def _on_apply_clicked(self) -> None:
        """Aplica los cambios, emite la señal y cierra el diálogo."""
        text = self.text_edit.toPlainText().strip()
        settings = self.get_current_settings()
        self.settings_applied.emit(text, settings)
        self.accept()
