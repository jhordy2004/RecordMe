"""Estado de renderizado inmutable para comunicación segura UI -> Compositor."""

from dataclasses import dataclass, field

from recordme.utils.geometry import Rect


@dataclass(frozen=True)
class CameraLayout:
    """Configuración de renderizado de la cámara en el compositor."""
    enabled: bool = False
    shape: str = "rect"  # rect (por defecto sin bordes), circle
    center_norm_x: float = 0.85
    center_norm_y: float = 0.80
    size_pct: int = 20
    mirror: bool = True
    border_enabled: bool = False
    border_width: int = 0
    border_color: str = "#FFFFFF"
    name_enabled: bool = False
    name_text: str = ""
    name_position: str = "bottom_left"
    virtual_bg_image: str | None = None


@dataclass(frozen=True)
class CensorRegion:
    """Región de censura en coordenadas de pantalla origen."""
    id: str
    rect: Rect
    mode: str = "blur"  # blur, pixelate, solid
    blur_strength: int = 45
    pixel_size: int = 18
    active: bool = True


@dataclass(frozen=True)
class RenderState:
    """Snapshot inmutable consumido por el hilo del compositor."""
    # Área de captura de pantalla
    capture_region: Rect
    output_width: int
    output_height: int

    # Zoom
    target_zoom: float = 1.0
    target_center_x: float = 0.5
    target_center_y: float = 0.5
    follow_cursor: bool = False
    cursor_x: int = 0
    cursor_y: int = 0

    # Capas
    camera: CameraLayout = field(default_factory=CameraLayout)
    censor_regions: tuple[CensorRegion, ...] = field(default_factory=tuple)

    # Indicadores
    show_cursor: bool = True
    is_paused: bool = False
