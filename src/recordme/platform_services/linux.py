"""Servicios de plataforma para Linux (X11 y Wayland con estrategia de colocación fuera del área)."""

import logging
import os
from typing import Any

from recordme.platform_services.base import PlatformServices
from recordme.utils.geometry import Rect

logger = logging.getLogger(__name__)


class LinuxPlatformServices(PlatformServices):
    """Implementación de servicios de plataforma para Linux (X11 y Wayland experimental)."""

    def __init__(self) -> None:
        self.session_type = os.environ.get("XDG_SESSION_TYPE", "x11").lower()
        self.is_wayland = "wayland" in self.session_type or bool(os.environ.get("WAYLAND_DISPLAY"))
        self._managed_widgets: list[Any] = []
        logger.info("LinuxPlatformServices inicializado. Tipo de sesión: %s (Wayland=%s)", self.session_type, self.is_wayland)

    def set_dpi_awareness(self) -> bool:
        """En Linux la escala DPI depende de las variables de entorno de Qt y del servidor gráfico."""
        return True

    def has_native_window_exclusion(self) -> bool:
        """Indica si el servidor gráfico soporta exclusión directa de ventanas propias (False en Linux)."""
        return False

    def get_system_warning(self) -> str:
        """Mensaje de limitación y recomendación técnica para la UI en entornos Linux."""
        if self.is_wayland:
            return (
                "Entorno Wayland detectado: Las ventanas auxiliares se ubican automáticamente fuera del área "
                "seleccionada. Para exclusión total sin bordes, se recomienda usar una sesión X11 o un segundo monitor."
            )
        return (
            "Entorno X11 detectado: El servidor gráfico no permite exclusión nativa de ventanas por afinidad. "
            "RecordMe colocará la barra y el teleprompter fuera del recuadro grabado automáticamente."
        )

    def exclude_window_from_capture(self, widget: Any) -> bool:
        """En Linux no hay API nativa (como WDA_EXCLUDEFROMCAPTURE).

        Se activa la estrategia de colocación fuera del área de grabación para que las
        ventanas de control nunca se superpongan a los píxeles capturados.
        """
        if widget not in self._managed_widgets:
            self._managed_widgets.append(widget)
        logger.info(
            "Ventana registrada para estrategia de colocación fuera del área en Linux (%s).",
            widget.__class__.__name__,
        )
        return True

    def reposition_outside_region(self, widget: Any, region: Rect, screen_geom: Rect) -> None:
        """Calcula y mueve la ventana fuera del rectángulo grabado para no salir en el video."""
        try:
            if not hasattr(widget, "geometry") or not hasattr(widget, "move"):
                return

            w_geom = widget.geometry()
            w_w = w_geom.width()
            w_h = w_geom.height()

            # 1. Intentar colocar arriba del área grabada si hay espacio suficiente
            if region.y >= w_h + 10:
                widget.move(region.x + max(0, (region.width - w_w) // 2), region.y - w_h - 10)
                logger.debug("Widget reposicionado arriba de la región grabada: y=%d", region.y - w_h - 10)
                return

            # 2. Intentar colocar abajo del área grabada
            space_below = screen_geom.height - (region.y + region.height)
            if space_below >= w_h + 10:
                widget.move(region.x + max(0, (region.width - w_w) // 2), region.y + region.height + 10)
                logger.debug("Widget reposicionado abajo de la región grabada: y=%d", region.y + region.height + 10)
                return

            # 3. Intentar colocar a la derecha
            space_right = screen_geom.width - (region.x + region.width)
            if space_right >= w_w + 10:
                widget.move(region.x + region.width + 10, region.y)
                logger.debug("Widget reposicionado a la derecha de la región grabada")
                return

            # 4. Intentar colocar a la izquierda
            if region.x >= w_w + 10:
                widget.move(region.x - w_w - 10, region.y)
                logger.debug("Widget reposicionado a la izquierda de la región grabada")
                return
        except Exception as e:
            logger.debug("Error aplicando reposicionamiento en Linux: %s", e)

    def apply_blur_behind(self, widget: Any) -> bool:
        """En Linux el blur depende del compositor de ventanas (KWin, Picom, Mutter)."""
        return False

    def request_permissions(self) -> dict[str, bool]:
        """Linux normalmente no requiere permisos a nivel de OS salvo Portales Wayland."""
        return {
            "screen_capture": True,
            "camera": True,
            "microphone": True,
            "accessibility": True,
        }
