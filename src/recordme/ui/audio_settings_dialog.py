"""Diálogo interactivo de configuración de audio: micrófono, loopback del sistema y supresión de ruido."""

import logging
import threading
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from recordme.audio.devices import AudioDeviceInfo, list_input_devices
from recordme.audio.mic_recorder import _patch_soundcard_com
from recordme.config.settings import AudioSettings
from recordme.constants import APP_NAME
from recordme.platform_services.factory import get_platform_services
from recordme.resources import get_app_icon
from recordme.utils.i18n import tr

logger = logging.getLogger(__name__)

_patch_soundcard_com()


class _AudioLevelMeter(QWidget):
    """Barra gráfica de nivel de audio en tiempo real estilo VU meter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(12)
        self.setMinimumWidth(200)
        self._level: float = 0.0  # 0.0 a 1.0

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Fondo
        painter.setBrush(QColor(30, 30, 30))
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        painter.drawRoundedRect(0, 0, w, h, 3, 3)

        # Relleno del nivel
        fill_w = int(w * self._level)
        if fill_w > 0:
            if self._level > 0.85:
                color = QColor(255, 75, 75)  # Rojo peak
            elif self._level > 0.6:
                color = QColor(255, 180, 0)   # Amarillo advertencia
            else:
                color = QColor(0, 200, 120)   # Verde óptimo
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(1, 1, max(1, fill_w - 2), h - 2, 2, 2)


class AudioSettingsDialog(QDialog):
    """Panel modal para configurar el modo de grabación de audio, loopback del sistema y supresión de ruido."""

    settings_applied = Signal(AudioSettings)

    def __init__(
        self,
        current_settings: AudioSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = current_settings
        self.platform_services = get_platform_services()

        self.setWindowTitle(f"{tr('audio_dialog_title')} — {APP_NAME}")
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(480)

        self._available_devices: list[AudioDeviceInfo] = []
        self._test_stream: Any = None
        self._mic_level: float = 0.0
        self._sys_level: float = 0.0
        self._monitor_active: bool = False
        self._sys_thread: threading.Thread | None = None
        self._meter_timer: QTimer = QTimer(self)
        self._meter_timer.setInterval(33)  # ~30 FPS
        self._meter_timer.timeout.connect(self._on_meter_tick)

        self._init_ui()
        self._populate_devices()

    def _init_ui(self) -> None:
        """Construye la interfaz de usuario con diseño moderno y tema oscuro."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(22, 22, 22, 22)

        # 1. Cabecera
        header_label = QLabel(tr("audio_dialog_header"))
        header_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        layout.addWidget(header_label)

        # 2. Modo de grabación (Micrófono vs Micrófono + Sistema)
        mode_box = QWidget()
        mode_layout = QVBoxLayout(mode_box)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)

        mode_title = QLabel(tr("audio_mode_label"))
        mode_title.setStyleSheet("font-weight: bold; color: #00B4D8; font-size: 13px;")
        mode_layout.addWidget(mode_title)

        self.radio_group = QButtonGroup(self)

        self.radio_mic_only = QRadioButton(tr("audio_mode_mic_only"))
        self.radio_mic_only.setCursor(Qt.CursorShape.PointingHandCursor)
        self.radio_mic_only.setStyleSheet("color: #FFFFFF; font-size: 12px; padding: 3px 0;")
        self.radio_group.addButton(self.radio_mic_only, 0)
        mode_layout.addWidget(self.radio_mic_only)

        self.radio_mic_and_sys = QRadioButton(tr("audio_mode_mic_and_system"))
        self.radio_mic_and_sys.setCursor(Qt.CursorShape.PointingHandCursor)
        self.radio_mic_and_sys.setStyleSheet("color: #FFFFFF; font-size: 12px; padding: 3px 0;")
        self.radio_group.addButton(self.radio_mic_and_sys, 1)
        mode_layout.addWidget(self.radio_mic_and_sys)

        mode_help = QLabel(tr("audio_mode_help"))
        mode_help.setWordWrap(True)
        mode_help.setStyleSheet("color: #888888; font-size: 11px; margin-left: 20px; line-height: 1.3;")
        mode_layout.addWidget(mode_help)

        layout.addWidget(mode_box)

        # Estado inicial de selección de modo
        if self.settings.mode == "mic_and_system":
            self.radio_mic_and_sys.setChecked(True)
        else:
            self.radio_mic_only.setChecked(True)

        self.radio_mic_only.toggled.connect(self._on_mode_toggled)
        self.radio_mic_and_sys.toggled.connect(self._on_mode_toggled)

        # 3. Dispositivo de micrófono
        dev_layout = QVBoxLayout()
        dev_layout.setSpacing(6)
        dev_title = QLabel(tr("audio_device_label"))
        dev_title.setStyleSheet("font-weight: bold; color: #DDDDDD; font-size: 12px;")
        dev_layout.addWidget(dev_title)

        self.combo_device = QComboBox()
        self.combo_device.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_device.setStyleSheet(
            "QComboBox { background: #262626; color: #FFFFFF; border: 1px solid #444; border-radius: 4px; padding: 6px 10px; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { background: #222; color: #FFF; selection-background-color: #00B4D8; }"
        )
        self.combo_device.currentIndexChanged.connect(self._restart_mic_monitor)
        dev_layout.addWidget(self.combo_device)
        layout.addLayout(dev_layout)

        # 4. Supresión Inteligente de Ruido
        noise_box = QWidget()
        noise_layout = QVBoxLayout(noise_box)
        noise_layout.setContentsMargins(0, 4, 0, 0)
        noise_layout.setSpacing(4)

        noise_title = QLabel(tr("audio_noise_reduction_label"))
        noise_title.setStyleSheet("font-weight: bold; color: #00B4D8; font-size: 12px;")
        noise_layout.addWidget(noise_title)

        self.check_noise = QCheckBox(tr("audio_noise_reduction_checkbox"))
        self.check_noise.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_noise.setChecked(self.settings.noise_reduction)
        self.check_noise.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: 500;")
        noise_layout.addWidget(self.check_noise)

        noise_help = QLabel(tr("audio_noise_reduction_help"))
        noise_help.setWordWrap(True)
        noise_help.setStyleSheet("color: #888888; font-size: 11px; margin-left: 20px;")
        noise_layout.addWidget(noise_help)

        layout.addWidget(noise_box)

        # 5. Nivel / Ganancia y medidor de prueba
        gain_box = QWidget()
        gain_layout = QVBoxLayout(gain_box)
        gain_layout.setContentsMargins(0, 4, 0, 0)
        gain_layout.setSpacing(6)

        gain_header = QHBoxLayout()
        gain_title = QLabel(tr("audio_volume_label"))
        gain_title.setStyleSheet("font-weight: bold; color: #DDDDDD; font-size: 12px;")
        gain_header.addWidget(gain_title)

        self.label_gain_val = QLabel("100%")
        self.label_gain_val.setStyleSheet("color: #00B4D8; font-size: 12px; font-weight: bold;")
        gain_header.addWidget(self.label_gain_val, 0, Qt.AlignmentFlag.AlignRight)
        gain_layout.addLayout(gain_header)

        self.slider_gain = QSlider(Qt.Orientation.Horizontal)
        self.slider_gain.setRange(0, 150)
        initial_pct = int(round(100.0 * (10.0 ** (self.settings.mic_gain_db / 20.0)))) if self.settings.mic_gain_db != 0 else 100
        self.slider_gain.setValue(max(0, min(150, initial_pct)))
        self.slider_gain.valueChanged.connect(self._on_gain_changed)
        gain_layout.addWidget(self.slider_gain)

        # Barra gráfica en tiempo real
        self.level_meter = _AudioLevelMeter(self)
        gain_layout.addWidget(self.level_meter)

        layout.addWidget(gain_box)

        # 6. Botones de acción (Guardar / Cancelar)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton(tr("btn_cancel"))
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background: #333333; color: #DDDDDD; border-radius: 4px; padding: 8px 18px; font-size: 12px; }"
            "QPushButton:hover { background: #444444; }"
        )
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(tr("btn_accept"))
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet(
            "QPushButton { background: #00B4D8; color: #FFFFFF; font-weight: bold; border-radius: 4px; padding: 8px 22px; font-size: 12px; }"
            "QPushButton:hover { background: #0096C7; }"
        )
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

        # Iniciar monitoreo suave de nivel de micrófono para la barra VU
        self._start_level_monitor()

    def _populate_devices(self) -> None:
        """Carga los dispositivos de entrada de micrófono disponibles."""
        self.combo_device.clear()
        self.combo_device.addItem(f"🎙 {tr('audio_device_default')}", "default")

        try:
            self._available_devices = list_input_devices()
            for dev in self._available_devices:
                self.combo_device.addItem(f"🎙 {dev.name}", str(dev.index))
        except Exception as e:
            logger.warning("Error listando dispositivos de micrófono: %s", e)

        # Seleccionar el dispositivo actual
        cur_dev = self.settings.mic_device
        for idx in range(self.combo_device.count()):
            if self.combo_device.itemData(idx) == cur_dev:
                self.combo_device.setCurrentIndex(idx)
                break

    def _on_gain_changed(self, value: int) -> None:
        """Actualiza la etiqueta visual de porcentaje de ganancia."""
        self.label_gain_val.setText(f"{value}%")

    def _on_meter_tick(self) -> None:
        """Actualiza la barra gráfica VU en el hilo principal de Qt de manera suave y segura."""
        is_sys = self.radio_mic_and_sys.isChecked()
        sys_val = self._sys_level if is_sys else 0.0
        combined = max(self._mic_level, sys_val)
        self.level_meter.set_level(combined)

    def _on_mode_toggled(self) -> None:
        """Alterna el monitoreo de audio del sistema cuando el usuario cambia el radio botón."""
        if self.radio_mic_and_sys.isChecked():
            self._start_system_monitor()
        else:
            self._stop_system_monitor()

    def _start_level_monitor(self) -> None:
        """Inicia el monitoreo de audio (micrófono y opcionalmente loopback del sistema)."""
        self._monitor_active = True
        self._start_mic_monitor()
        if self.radio_mic_and_sys.isChecked():
            self._start_system_monitor()
        self._meter_timer.start()

    def _restart_mic_monitor(self) -> None:
        """Reinicia el monitor de micrófono cuando el usuario cambia de dispositivo en el combo."""
        self._stop_mic_monitor()
        if self._monitor_active:
            self._start_mic_monitor()

    def _start_mic_monitor(self) -> None:
        """Inicia el stream de captura de micrófono para la barra VU."""
        try:
            import numpy as np
            import sounddevice as sd

            dev_idx = None
            cur_data = self.combo_device.currentData()
            if cur_data and cur_data != "default":
                try:
                    dev_idx = int(cur_data)
                except ValueError:
                    pass

            def callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
                if status:
                    return
                try:
                    peak = float(np.max(np.abs(indata)))
                    if self.check_noise.isChecked():
                        if peak < 0.020:
                            peak = 0.0
                        else:
                            peak = min(1.0, (peak - 0.020) / (0.75 - 0.020))
                    self._mic_level = peak
                except Exception:
                    self._mic_level = 0.0

            self._test_stream = sd.InputStream(
                samplerate=44100,
                channels=1,
                device=dev_idx,
                callback=callback,
                dtype="float32",
                blocksize=1024,
            )
            self._test_stream.start()
        except Exception as e:
            logger.debug("No se pudo iniciar el monitor de nivel de micrófono: %s", e)

    def _stop_mic_monitor(self) -> None:
        """Detiene el stream de micrófono."""
        self._mic_level = 0.0
        if self._test_stream is not None:
            try:
                self._test_stream.stop()
                self._test_stream.close()
            except Exception:
                pass
            finally:
                self._test_stream = None

    def _start_system_monitor(self) -> None:
        """Inicia el hilo de monitoreo de loopback del sistema."""
        if self._sys_thread is not None and self._sys_thread.is_alive():
            return
        self._sys_thread = threading.Thread(
            target=self._system_level_loop,
            daemon=True,
            name="AudioDialog-SystemLevelThread",
        )
        self._sys_thread.start()

    def _stop_system_monitor(self) -> None:
        """Detiene el monitoreo de audio del sistema."""
        self._sys_level = 0.0
        if self._sys_thread is not None and self._sys_thread.is_alive():
            self._sys_thread.join(timeout=0.3)
            self._sys_thread = None

    def _system_level_loop(self) -> None:
        """Hilo de monitoreo del nivel de audio del sistema (loopback) para la barra VU."""
        com_initialized = False
        try:
            import sys
            if sys.platform == "win32":
                try:
                    import ctypes
                    res = ctypes.windll.ole32.CoInitializeEx(None, 0)
                    if res in (0, 1):
                        com_initialized = True
                except Exception:
                    pass

            import warnings

            import numpy as np
            import soundcard as sc

            speaker = sc.default_speaker()
            if not speaker:
                return
            loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)
            if not loopback:
                return

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="data discontinuity in recording")
                with loopback.recorder(samplerate=48000, channels=2, blocksize=9600) as rec:
                    while self._monitor_active:
                        data = rec.record(numframes=None)
                        if data is not None and len(data) > 0:
                            peak = float(np.max(np.abs(data)))
                            self._sys_level = peak
                        else:
                            self._sys_level = 0.0
        except Exception as e:
            logger.debug("Aviso en monitor loopback de diálogo: %s", e)
        finally:
            self._sys_level = 0.0
            if com_initialized:
                try:
                    import ctypes
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass

    def _stop_level_monitor(self) -> None:
        """Detiene completamente el monitoreo de prueba (micrófono y sistema)."""
        self._monitor_active = False
        if self._meter_timer.isActive():
            self._meter_timer.stop()
        self._stop_mic_monitor()
        self._stop_system_monitor()
        self.level_meter.set_level(0.0)

    def _on_save_clicked(self) -> None:
        """Construye y aplica los nuevos ajustes de audio."""
        import math

        mode = "mic_and_system" if self.radio_mic_and_sys.isChecked() else "mic_only"
        dev = str(self.combo_device.currentData())
        noise_red = self.check_noise.isChecked()

        pct = self.slider_gain.value()
        gain_db = 20.0 * math.log10(max(0.01, pct / 100.0)) if pct > 0 else -60.0

        new_settings = AudioSettings(
            mic_device=dev,
            mic_enabled=self.settings.mic_enabled,
            mic_gain_db=round(gain_db, 2),
            mode=mode,
            system_audio_enabled=(mode == "mic_and_system"),
            noise_reduction=noise_red,
        )

        self.settings = new_settings
        self.settings_applied.emit(new_settings)
        self.accept()

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        self._stop_level_monitor()
        super().closeEvent(event)

    def reject(self) -> None:
        self._stop_level_monitor()
        super().reject()
