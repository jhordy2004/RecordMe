"""Configuración de la aplicación con dataclasses y persistencia JSON tolerante a fallos."""

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from recordme.config.paths import get_config_dir, get_default_recordings_dir

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "settings.json"


@dataclass
class OutputSettings:
    """Ajustes de salida y codificación."""
    folder: str = field(default_factory=lambda: str(get_default_recordings_dir()))
    ask_where_to_save: bool = True
    filename_template: str = "Grabacion_{YYYY}-{MM}-{DD}_{HH}-{mm}-{ss}"
    fps: int = 30
    resolution: str = "native"  # native, 1080p, 720p
    quality: str = "high"  # low, medium, high, ultra
    encoder: str = "auto"  # auto, libx264, nvenc, qsv, amf


@dataclass
class AudioSettings:
    """Ajustes de audio."""
    mic_device: str = "default"
    mic_enabled: bool = True
    mic_gain_db: float = 0.0


@dataclass
class CameraPosition:
    """Posición relativa normalizada (0.0 a 1.0)."""
    x: float = 0.85
    y: float = 0.80


@dataclass
class CameraBorder:
    """Borde de la burbuja de cámara."""
    enabled: bool = False
    width: int = 0
    color: str = "#FFFFFF"


@dataclass
class CameraBackground:
    """Fondo virtual para la cámara."""
    mode: str = "none"  # none, blur, color, image
    color: str = "#1E1E1E"
    image: str | None = None
    blur_strength: int = 25


@dataclass
class CameraName:
    """Nombre superpuesto en la cámara."""
    enabled: bool = False
    text: str = ""
    position: str = "bottom_left"  # bottom_left, below, above


@dataclass
class CameraSettings:
    """Ajustes de cámara."""
    enabled: bool = False
    device: str = "default"
    shape: str = "rect"  # rect (por defecto sin bordes), circle
    size_pct: int = 18
    position: CameraPosition = field(default_factory=CameraPosition)
    mirror: bool = True
    border: CameraBorder = field(default_factory=CameraBorder)
    background: CameraBackground = field(default_factory=CameraBackground)
    name: CameraName = field(default_factory=CameraName)


@dataclass
class TeleprompterSettings:
    """Ajustes de teleprompter."""
    enabled: bool = False
    font_size: int = 34
    wpm: int = 130
    seconds_per_line: float = 3.5
    lines_visible: int = 2
    opacity: float = 0.78
    width_pct: int = 60
    position_x: float = 0.5
    position_y: float = 0.12
    mirror_text: bool = False
    countdown: bool = True
    last_script: str = ""


@dataclass
class ZoomSettings:
    """Ajustes de zoom en vivo."""
    level: float = 2.0
    tau_seconds: float = 0.35
    follow_cursor: bool = True
    deadzone_pct: int = 20


@dataclass
class CensorSettings:
    """Ajustes de censura."""
    mode: str = "blur"  # blur, pixelate, solid
    blur_strength: int = 45
    pixel_size: int = 18


@dataclass
class CursorSettings:
    """Ajustes de renderizado de cursor."""
    show: bool = True
    highlight_clicks: bool = False


@dataclass
class HotkeySettings:
    """Atajos de teclado globales."""
    start_stop: str = "<f9>"
    pause_resume: str = "<f10>"
    teleprompter: str = "<f8>"
    zoom_toggle: str = "<ctrl>+<shift>+z"
    zoom_region: str = "<ctrl>+<shift>+x"
    censor_add: str = "<ctrl>+<shift>+c"
    censor_clear: str = "<ctrl>+<shift>+v"


@dataclass
class AppSettings:
    """Configuración raíz de RecordMe."""
    language: str = "auto"
    output: OutputSettings = field(default_factory=OutputSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    camera: CameraSettings = field(default_factory=CameraSettings)
    teleprompter: TeleprompterSettings = field(default_factory=TeleprompterSettings)
    zoom: ZoomSettings = field(default_factory=ZoomSettings)
    censor: CensorSettings = field(default_factory=CensorSettings)
    cursor: CursorSettings = field(default_factory=CursorSettings)
    hotkeys: HotkeySettings = field(default_factory=HotkeySettings)

    @classmethod
    def load(cls, config_path: Path | None = None) -> "AppSettings":
        """Carga la configuración desde JSON. Si no existe o está corrupto, usa defaults."""
        if config_path is None:
            config_path = get_config_dir() / CONFIG_FILENAME

        if not config_path.exists():
            instance = cls()
            instance.save(config_path)
            return instance

        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            return cls._from_dict(data)
        except Exception as e:
            logger.warning("Error leyendo archivo de configuración (%s). Usando valores por defecto.", e)
            return cls()

    def save(self, config_path: Path | None = None) -> None:
        """Guarda la configuración en disco en formato JSON indentado."""
        if config_path is None:
            config_path = get_config_dir() / CONFIG_FILENAME

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("No se pudo guardar la configuración en %s: %s", config_path, e)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "AppSettings":
        """Reconstrucción defensiva de AppSettings a partir de un dict."""
        instance = cls()
        if not isinstance(data, dict):
            return instance

        raw_lang = data.get("language")
        if raw_lang in ("auto", "system", None) or raw_lang == "es":
            instance.language = "auto"
        else:
            instance.language = str(raw_lang)

        # Output
        if isinstance(data.get("output"), dict):
            out = data["output"]
            instance.output = OutputSettings(
                folder=str(out.get("folder", instance.output.folder)),
                ask_where_to_save=bool(out.get("ask_where_to_save", instance.output.ask_where_to_save)),
                filename_template=str(out.get("filename_template", instance.output.filename_template)),
                fps=int(out.get("fps", instance.output.fps)),
                resolution=str(out.get("resolution", instance.output.resolution)),
                quality=str(out.get("quality", instance.output.quality)),
                encoder=str(out.get("encoder", instance.output.encoder)),
            )

        # Audio
        if isinstance(data.get("audio"), dict):
            aud = data["audio"]
            instance.audio = AudioSettings(
                mic_device=str(aud.get("mic_device", instance.audio.mic_device)),
                mic_enabled=bool(aud.get("mic_enabled", instance.audio.mic_enabled)),
                mic_gain_db=float(aud.get("mic_gain_db", instance.audio.mic_gain_db)),
            )

        # Camera
        if isinstance(data.get("camera"), dict):
            cam = data["camera"]
            pos_dict = cam.get("position", {})
            border_dict = cam.get("border", {})
            bg_dict = cam.get("background", {})
            name_dict = cam.get("name", {})

            instance.camera = CameraSettings(
                enabled=bool(cam.get("enabled", instance.camera.enabled)),
                device=str(cam.get("device", instance.camera.device)),
                shape=str(cam.get("shape", instance.camera.shape)),
                size_pct=int(cam.get("size_pct", instance.camera.size_pct)),
                position=CameraPosition(
                    x=float(pos_dict.get("x", 0.85)),
                    y=float(pos_dict.get("y", 0.80)),
                ),
                mirror=bool(cam.get("mirror", instance.camera.mirror)),
                border=CameraBorder(
                    enabled=bool(border_dict.get("enabled", True)),
                    width=int(border_dict.get("width", 4)),
                    color=str(border_dict.get("color", "#FFFFFF")),
                ),
                background=CameraBackground(
                    mode=str(bg_dict.get("mode", "none")),
                    color=str(bg_dict.get("color", "#1E1E1E")),
                    image=bg_dict.get("image"),
                    blur_strength=int(bg_dict.get("blur_strength", 25)),
                ),
                name=CameraName(
                    enabled=bool(name_dict.get("enabled", False)),
                    text=str(name_dict.get("text", "")),
                    position=str(name_dict.get("position", "below")),
                ),
            )

        # Teleprompter
        if isinstance(data.get("teleprompter"), dict):
            tp = data["teleprompter"]
            instance.teleprompter = TeleprompterSettings(
                enabled=bool(tp.get("enabled", instance.teleprompter.enabled)),
                font_size=int(tp.get("font_size", instance.teleprompter.font_size)),
                wpm=int(tp.get("wpm", instance.teleprompter.wpm)),
                seconds_per_line=float(tp.get("seconds_per_line", instance.teleprompter.seconds_per_line)),
                lines_visible=max(1, min(5, int(tp.get("lines_visible", instance.teleprompter.lines_visible)))),
                opacity=float(tp.get("opacity", instance.teleprompter.opacity)),
                width_pct=int(tp.get("width_pct", instance.teleprompter.width_pct)),
                position_x=float(tp.get("position_x", instance.teleprompter.position_x)),
                position_y=float(tp.get("position_y", instance.teleprompter.position_y)),
                mirror_text=bool(tp.get("mirror_text", instance.teleprompter.mirror_text)),
                countdown=bool(tp.get("countdown", instance.teleprompter.countdown)),
                last_script=str(tp.get("last_script", instance.teleprompter.last_script)),
            )

        # Zoom
        if isinstance(data.get("zoom"), dict):
            zm = data["zoom"]
            instance.zoom = ZoomSettings(
                level=float(zm.get("level", instance.zoom.level)),
                tau_seconds=float(zm.get("tau_seconds", instance.zoom.tau_seconds)),
                follow_cursor=bool(zm.get("follow_cursor", instance.zoom.follow_cursor)),
                deadzone_pct=int(zm.get("deadzone_pct", instance.zoom.deadzone_pct)),
            )

        # Censor
        if isinstance(data.get("censor"), dict):
            cn = data["censor"]
            instance.censor = CensorSettings(
                mode=str(cn.get("mode", instance.censor.mode)),
                blur_strength=int(cn.get("blur_strength", instance.censor.blur_strength)),
                pixel_size=int(cn.get("pixel_size", instance.censor.pixel_size)),
            )

        # Cursor
        if isinstance(data.get("cursor"), dict):
            cr = data["cursor"]
            instance.cursor = CursorSettings(
                show=bool(cr.get("show", instance.cursor.show)),
                highlight_clicks=bool(cr.get("highlight_clicks", instance.cursor.highlight_clicks)),
            )

        # Hotkeys
        if isinstance(data.get("hotkeys"), dict):
            hk = data["hotkeys"]
            instance.hotkeys = HotkeySettings(
                start_stop=str(hk.get("start_stop", instance.hotkeys.start_stop)),
                pause_resume=str(hk.get("pause_resume", instance.hotkeys.pause_resume)),
                teleprompter=str(hk.get("teleprompter", instance.hotkeys.teleprompter)),
                zoom_toggle=str(hk.get("zoom_toggle", instance.hotkeys.zoom_toggle)),
                zoom_region=str(hk.get("zoom_region", instance.hotkeys.zoom_region)),
                censor_add=str(hk.get("censor_add", instance.hotkeys.censor_add)),
                censor_clear=str(hk.get("censor_clear", instance.hotkeys.censor_clear)),
            )

        return instance
