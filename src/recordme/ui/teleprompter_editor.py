"""Editor de teleprompter: carga de texto, ajuste de velocidad en segundos, tamaño y prueba directa en el panel."""

import logging
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QMouseEvent
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
from recordme.platform_services.factory import get_platform_services
from recordme.utils.i18n import tr

logger = logging.getLogger(__name__)


class ContinuousValueSlider(QSlider):
    """Slider de precisión continua (paso 1 a 1) que sitúa el valor directamente donde se hace clic o arrastra."""

    def __init__(self, min_val: int = 16, max_val: int = 50, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(min_val, max_val)
        self.setSingleStep(1)
        self.setPageStep(1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _coord_to_val(self, x: float) -> int:
        w = max(1, self.width())
        pct = max(0.0, min(1.0, x / w))
        return int(round(self.minimum() + pct * (self.maximum() - self.minimum())))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            val = self._coord_to_val(event.position().x())
            self.setValue(val)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            val = self._coord_to_val(event.position().x())
            self.setValue(val)
            event.accept()
            return
        super().mouseMoveEvent(event)


class SteppedLinesSlider(QSlider):
    """Slider de líneas visibles de 20% a 100% con saltos forzados de 20% por paso (1 a 5 líneas)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(20, 100)
        self.setSingleStep(20)
        self.setPageStep(20)
        self.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.setTickInterval(20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @staticmethod
    def snap_percentage(pct: float) -> int:
        """Aplica la regla de saltos discretos por tramos de 20%:

        <= 20% -> 20% (1 línea)
        21% a 40% -> 40% (2 líneas)
        41% a 60% -> 60% (3 líneas)
        61% a 80% -> 80% (4 líneas)
        81% a 100% -> 100% (5 líneas)
        """
        if pct <= 20.0:
            return 20
        elif pct <= 40.0:
            return 40
        elif pct <= 60.0:
            return 60
        elif pct <= 80.0:
            return 80
        else:
            return 100

    def _coord_to_snapped_val(self, x: float) -> int:
        w = max(1, self.width())
        pct = max(0.0, min(100.0, (x / w) * 100.0))
        return self.snap_percentage(pct)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            val = self._coord_to_snapped_val(event.position().x())
            self.setValue(val)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            val = self._coord_to_snapped_val(event.position().x())
            self.setValue(val)
            event.accept()
            return
        super().mouseMoveEvent(event)


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
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
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
        title_label = QLabel(tr("tp_title"))
        title_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #E0E0E0;")
        top_bar.addWidget(title_label)
        top_bar.addStretch()

        self.btn_open = QPushButton(tr("tp_open_txt"))
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.clicked.connect(self._open_file)
        top_bar.addWidget(self.btn_open)

        self.btn_save_script = QPushButton(tr("tp_save_script"))
        self.btn_save_script.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.sec_slider.setCursor(Qt.CursorShape.PointingHandCursor)
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

        # 2. Tamaño de fuente (de 16 a 50 px, de 1 en 1 sin saltos de página)
        font_box = QHBoxLayout()
        self.font_slider = ContinuousValueSlider(16, 50)
        self.font_slider.setValue(self.settings.font_size)
        self.font_spin = QSpinBox()
        self.font_spin.setRange(16, 50)
        self.font_spin.setSingleStep(1)
        self.font_spin.setValue(self.settings.font_size)
        self.font_spin.setSuffix(" px")
        self.font_slider.valueChanged.connect(self.font_spin.setValue)
        self.font_spin.valueChanged.connect(self.font_slider.setValue)
        self.font_spin.valueChanged.connect(self._update_editor_font)
        font_box.addWidget(self.font_slider, stretch=1)
        font_box.addWidget(self.font_spin)
        form_layout.addRow(tr("tp_font_size"), font_box)

        # 3. Líneas visibles (1 a 5 líneas con saltos escalonados del 20%)
        lines_box = QHBoxLayout()
        self.lines_slider = SteppedLinesSlider()
        init_lines = max(1, min(5, self.settings.lines_visible))
        self.lines_slider.setValue(init_lines * 20)

        self.lines_spin = QSpinBox()
        self.lines_spin.setRange(1, 5)
        self.lines_spin.setValue(init_lines)
        self.lines_spin.setSuffix(f" {tr('tp_lines_suffix')}")

        self.lines_slider.valueChanged.connect(self._on_lines_slider_changed)
        self.lines_spin.valueChanged.connect(self._on_lines_spin_changed)

        lines_box.addWidget(self.lines_slider, stretch=1)
        lines_box.addWidget(self.lines_spin)
        form_layout.addRow(tr("tp_lines_visible"), lines_box)

        # 4. Opacidad
        opacity_box = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test.setStyleSheet(
            "background-color: #2E7D32; color: #FFFFFF; font-weight: bold; padding: 8px 18px; border-radius: 6px;"
        )
        self.btn_test.clicked.connect(self._toggle_in_panel_test)
        btn_layout.addWidget(self.btn_test)

        btn_layout.addStretch()

        self.btn_cancel = QPushButton(tr("btn_cancel"))
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_apply = QPushButton(tr("tp_apply"))
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.setStyleSheet(
            "background-color: #007ACC; color: #FFFFFF; font-weight: bold; padding: 8px 22px; border-radius: 6px;"
        )
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)

    def _on_lines_slider_changed(self, val: int) -> None:
        """Asegura el enganche exacto al 20%, 40%, 60%, 80% o 100% y actualiza el spinbox."""
        snapped = SteppedLinesSlider.snap_percentage(val)
        if val != snapped:
            self.lines_slider.blockSignals(True)
            self.lines_slider.setValue(snapped)
            self.lines_slider.blockSignals(False)
        lines = max(1, min(5, snapped // 20))
        if self.lines_spin.value() != lines:
            self.lines_spin.blockSignals(True)
            self.lines_spin.setValue(lines)
            self.lines_spin.blockSignals(False)

    def _on_lines_spin_changed(self, lines: int) -> None:
        """Sincroniza el slider al valor porcentual correspondiente a la cantidad de líneas."""
        lines = max(1, min(5, lines))
        target_pct = lines * 20
        if self.lines_slider.value() != target_pct:
            self.lines_slider.blockSignals(True)
            self.lines_slider.setValue(target_pct)
            self.lines_slider.blockSignals(False)

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

    def _extract_text_from_file(self, file_path: Path) -> str | None:
        """Extrae texto de archivos .txt, .docx y .doc con fallbacks resilientes."""
        suffix = file_path.suffix.lower()

        if suffix == ".docx":
            # 1. Intentar con python-docx si está disponible
            try:
                import docx
                doc = docx.Document(str(file_path))
                paras = [p.text for p in doc.paragraphs if p.text.strip()]
                if paras:
                    return "\n\n".join(paras)
            except Exception as e:
                logger.debug("Fallo lectura con python-docx: %s, probando parseo XML nativo...", e)

            # 2. Fallback nativo: descompresión ZIP y lectura de word/document.xml
            try:
                import xml.etree.ElementTree as ET
                import zipfile

                with zipfile.ZipFile(str(file_path)) as z:
                    xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    paras = []
                    for elem in tree.iter():
                        if elem.tag.endswith("}p"):
                            texts = [node.text for node in elem.iter() if node.tag.endswith("}t") and node.text]
                            line = "".join(texts).strip()
                            if line:
                                paras.append(line)
                    if paras:
                        return "\n\n".join(paras)
            except Exception as e:
                logger.error("No se pudo extraer texto del archivo .docx: %s", e)
                return None

        elif suffix == ".doc":
            # Para archivos .doc binarios heredados, extraer texto legible
            try:
                raw_bytes = file_path.read_bytes()
                text = raw_bytes.decode("latin-1", errors="ignore")
                cleaned = "".join(ch if (ch.isalnum() or ch in " \n\r\t.,;:?!-()\"'") else " " for ch in text)
                lines = [line.strip() for line in cleaned.splitlines() if len(line.strip()) > 3]
                if lines:
                    return "\n\n".join(lines)
            except Exception as e:
                logger.error("No se pudo extraer texto del archivo .doc: %s", e)
                return None

        else:
            # Archivo de texto (.txt)
            for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
                try:
                    return file_path.read_text(encoding=enc)
                except (UnicodeDecodeError, Exception):
                    continue

        return None

    def _open_file(self) -> None:
        """Abre un diálogo para cargar un archivo de texto .txt o Word (.docx, .doc)."""
        filter_str = (
            "Documentos soportados (*.txt *.docx *.doc);;"
            "Archivos de texto (*.txt);;"
            "Documentos de Word (*.docx *.doc);;"
            "Todos los archivos (*.*)"
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("tp_open_txt"),
            str(get_scripts_dir()),
            filter_str,
        )
        if path:
            text = self._extract_text_from_file(Path(path))
            if text is not None:
                self.text_edit.setPlainText(text)
            else:
                logger.warning("No se pudo extraer texto del archivo: %s", path)

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
        lines = max(1, min(5, settings.lines_visible))
        self.lines_spin.setValue(lines)
        self.lines_slider.setValue(lines * 20)
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

    def showEvent(self, event: Any) -> None:  # noqa: N802
        """Excluye el editor de teleprompter de la captura de pantalla."""
        super().showEvent(event)
        try:
            get_platform_services().exclude_window_from_capture(self)
        except Exception as e:
            logger.debug("No se pudo excluir TeleprompterEditorDialog de la captura: %s", e)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Asegura detener el timer al cerrar."""
        self._stop_test_timer()
        super().closeEvent(event)
