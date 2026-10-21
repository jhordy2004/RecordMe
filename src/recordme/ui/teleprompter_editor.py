"""Editor de teleprompter: carga de texto, ajuste de velocidad en segundos, tamaño y prueba directa en el panel."""

import logging
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
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
from recordme.utils.i18n import tr

logger = logging.getLogger(__name__)


class TeleprompterEditorDialog(QDialog):
    """Diálogo de edición y configuración del teleprompter con previsualización interactiva in situ."""

    settings_applied = Signal(str, TeleprompterSettings)
    test_requested = Signal(str, TeleprompterSettings)
    stop_test_requested = Signal()

    def __init__(
        self,
        current_text: str,
        settings: TeleprompterSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self._is_testing = False

        self._test_timer = QTimer(self)
        self._test_timer.setInterval(33)  # ~30 FPS
        self._test_timer.timeout.connect(self._on_test_scroll_tick)
        self._last_tick_time = 0.0
        self._sub_pixel_scroll = 0.0

        self.setWindowTitle(f"{tr('tp_title')} — {APP_NAME}")
        self.resize(740, 580)
        self.setMinimumSize(620, 500)

        self._init_ui(current_text)
        self._update_stats()
        self._update_editor_font()

    def _init_ui(self, initial_text: str) -> None:
        """Construye los controles y el área de edición."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Barra superior con botones de guion
        top_bar = QHBoxLayout()
        title_label = QLabel(tr("tp_header"))
        title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #FFFFFF;")
        top_bar.addWidget(title_label)
        top_bar.addStretch()

        self.btn_open = QPushButton(tr("tp_open_txt"))
        self.btn_open.clicked.connect(self._open_file)
        top_bar.addWidget(self.btn_open)

        self.btn_save_script = QPushButton(tr("tp_save_script"))
        self.btn_save_script.clicked.connect(self._save_file)
        top_bar.addWidget(self.btn_save_script)

        layout.addLayout(top_bar)

        # Editor de texto / vista previa interactiva
        self.text_edit = QTextEdit(self)
        self.text_edit.setPlaceholderText(tr("tp_placeholder"))
        self.text_edit.setPlainText(initial_text)
        self.text_edit.textChanged.connect(self._update_stats)
        layout.addWidget(self.text_edit, stretch=1)

        # Contador de palabras y tiempo estimado en segundos
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #00B4D8; font-weight: bold; font-size: 13px;")
        layout.addWidget(self.stats_label)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Formulario de ajustes
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 1. Velocidad en Segundos por línea (1.0s a 8.0s)
        sec_box = QHBoxLayout()
        self.sec_slider = QSlider(Qt.Orientation.Horizontal)
        self.sec_slider.setRange(10, 80)
        initial_tenths = int(self.settings.seconds_per_line * 10)
        self.sec_slider.setValue(max(10, min(initial_tenths, 80)))

        self.sec_spin = QDoubleSpinBox()
        self.sec_spin.setRange(1.0, 8.0)
        self.sec_spin.setSingleStep(0.5)
        self.sec_spin.setValue(self.settings.seconds_per_line)
        self.sec_spin.setSuffix(f" {tr('tp_sec_per_line')}")

        self.sec_slider.valueChanged.connect(lambda val: self.sec_spin.setValue(val / 10.0))
        self.sec_spin.valueChanged.connect(lambda val: self.sec_slider.setValue(int(val * 10)))
        self.sec_spin.valueChanged.connect(self._update_stats)

        sec_box.addWidget(self.sec_slider, stretch=1)
        sec_box.addWidget(self.sec_spin)
        form_layout.addRow(tr("tp_speed"), sec_box)

        # 2. Tamaño de fuente
        font_box = QHBoxLayout()
        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(16, 50)
        self.font_slider.setValue(self.settings.font_size)
        self.font_spin = QSpinBox()
        self.font_spin.setRange(16, 50)
        self.font_spin.setValue(self.settings.font_size)
        self.font_spin.setSuffix(" px")
        self.font_slider.valueChanged.connect(self.font_spin.setValue)
        self.font_spin.valueChanged.connect(self.font_slider.setValue)
        self.font_spin.valueChanged.connect(self._update_editor_font)
        font_box.addWidget(self.font_slider, stretch=1)
        font_box.addWidget(self.font_spin)
        form_layout.addRow(tr("tp_font_size"), font_box)

        # 3. Líneas visibles
        lines_box = QHBoxLayout()
        self.lines_slider = QSlider(Qt.Orientation.Horizontal)
        self.lines_slider.setRange(1, 3)
        self.lines_slider.setValue(self.settings.lines_visible)
        self.lines_spin = QSpinBox()
        self.lines_spin.setRange(1, 3)
        self.lines_spin.setValue(self.settings.lines_visible)
        self.lines_spin.setSuffix(f" {tr('tp_lines_suffix')}")
        self.lines_slider.valueChanged.connect(self.lines_spin.setValue)
        self.lines_spin.valueChanged.connect(self.lines_slider.setValue)
        lines_box.addWidget(self.lines_slider, stretch=1)
        lines_box.addWidget(self.lines_spin)
        form_layout.addRow(tr("tp_lines_visible"), lines_box)

        # 4. Opacidad
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
        form_layout.addRow(tr("tp_opacity"), opacity_box)

        layout.addLayout(form_layout)

        # Botones inferiores de acción
        btn_layout = QHBoxLayout()
        self.btn_test = QPushButton(tr("tp_test"))
        self.btn_test.setStyleSheet(
            "background-color: #2E7D32; color: #FFFFFF; font-weight: bold; padding: 8px 18px; border-radius: 6px;"
        )
        self.btn_test.clicked.connect(self._toggle_in_panel_test)
        btn_layout.addWidget(self.btn_test)

        btn_layout.addStretch()

        self.btn_cancel = QPushButton(tr("btn_cancel"))
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_apply = QPushButton(tr("tp_apply"))
        self.btn_apply.setStyleSheet(
            "background-color: #007ACC; color: #FFFFFF; font-weight: bold; padding: 8px 22px; border-radius: 6px;"
        )
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)

    def _update_editor_font(self) -> None:
        """Aplica el tamaño de letra seleccionado directamente al editor de texto."""
        font_size = self.font_spin.value()
        self.text_edit.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3A3A3A;
                border-radius: 8px;
                padding: 12px;
                font-size: {font_size}px;
                font-family: 'Segoe UI', sans-serif;
                line-height: 1.4;
            }}
            """
        )

    def _update_stats(self) -> None:
        """Calcula el número de palabras y la duración total estimada en segundos."""
        text = self.text_edit.toPlainText().strip()
        words = len(text.split()) if text else 0
        sec_per_line = max(0.5, self.sec_spin.value())

        lines_count = max(1, int(words / 7.5)) if words > 0 else 0
        total_seconds = int(lines_count * sec_per_line)
        mins = total_seconds // 60
        secs = total_seconds % 60
        self.stats_label.setText(
            tr("tp_stats", words=words, seconds=total_seconds, mins=mins, secs=secs)
        )

    def _toggle_in_panel_test(self) -> None:
        """Inicia o detiene la prueba de scroll continuo directamente dentro del editor."""
        if not self._is_testing:
            self._is_testing = True
            self.btn_test.setText(tr("tp_stop_test"))
            self.btn_test.setStyleSheet(
                "background-color: #C62828; color: #FFFFFF; font-weight: bold; padding: 8px 18px; border-radius: 6px;"
            )
            self._last_tick_time = time.perf_counter()
            self._sub_pixel_scroll = float(self.text_edit.verticalScrollBar().value())
            self._test_timer.start()
        else:
            self._stop_test_timer()

    def _stop_test_timer(self) -> None:
        """Detiene el temporizador de prueba interna."""
        self._is_testing = False
        self._test_timer.stop()
        self.btn_test.setText(tr("tp_test"))
        self.btn_test.setStyleSheet(
            "background-color: #2E7D32; color: #FFFFFF; font-weight: bold; padding: 8px 18px; border-radius: 6px;"
        )

    def _on_test_scroll_tick(self) -> None:
        """Avanza el scroll del editor de texto de forma suave a la velocidad elegida."""
        now = time.perf_counter()
        dt = now - self._last_tick_time
        self._last_tick_time = now

        sec_per_line = max(0.5, self.sec_spin.value())
        font_size = self.font_spin.value()
        line_height = font_size * 1.4

        # Píxeles por segundo
        px_per_sec = line_height / sec_per_line
        self._sub_pixel_scroll += px_per_sec * dt

        sb = self.text_edit.verticalScrollBar()
        max_scroll = sb.maximum()
        if max_scroll > 0:
            if self._sub_pixel_scroll > max_scroll:
                self._sub_pixel_scroll = 0.0
            sb.setValue(int(self._sub_pixel_scroll))
        else:
            # Si no hay scroll suficiente, avanzar suavemente
            pass

    def _open_file(self) -> None:
        """Abre un diálogo para cargar un archivo de texto .txt."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("tp_open_txt"),
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
            tr("tp_save_script"),
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
        sec_per_line = self.sec_spin.value()
        derived_wpm = max(40, min(300, int((7.5 / sec_per_line) * 60)))

        return TeleprompterSettings(
            enabled=True,
            font_size=self.font_spin.value(),
            wpm=derived_wpm,
            seconds_per_line=sec_per_line,
            lines_visible=self.lines_spin.value(),
            opacity=self.opacity_spin.value() / 100.0,
            width_pct=self.settings.width_pct,
            position_x=self.settings.position_x,
            position_y=self.settings.position_y,
            last_script=self.text_edit.toPlainText(),
        )

    def _toggle_test(self) -> None:
        """Compatibilidad con API de pruebas unitarias."""
        self._toggle_in_panel_test()

    def update_from_settings(self, settings: TeleprompterSettings) -> None:
        """Actualiza los campos del editor a partir de un objeto de ajustes."""
        self.settings = settings
        if settings.last_script:
            self.text_edit.setPlainText(settings.last_script)
        self.sec_spin.setValue(settings.seconds_per_line)
        self.font_spin.setValue(settings.font_size)
        self.lines_spin.setValue(settings.lines_visible)
        self.opacity_spin.setValue(int(settings.opacity * 100))
        self._update_stats()
        self._update_editor_font()

    def _on_cancel_clicked(self) -> None:
        """Cierra el diálogo descartando cambios no aplicados."""
        self._stop_test_timer()
        self.reject()

    def _on_apply_clicked(self) -> None:
        """Aplica los cambios, emite la señal y cierra el diálogo sin cerrar la app."""
        self._stop_test_timer()
        text = self.text_edit.toPlainText().strip()
        settings = self.get_current_settings()
        self.settings_applied.emit(text, settings)
        self.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Asegura detener el timer al cerrar."""
        self._stop_test_timer()
        super().closeEvent(event)
