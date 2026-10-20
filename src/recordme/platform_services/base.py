"""Protocolo para servicios dependientes de la plataforma (SO)."""

from typing import Any, Protocol


class PlatformServices(Protocol):
    """Protocolo de servicios específicos del sistema operativo."""

    def exclude_window_from_capture(self, widget: Any) -> bool:
        """Excluye la ventana Qt (o HWND) dada de las capturas de pantalla/video del sistema."""
        ...

    def apply_blur_behind(self, widget: Any) -> bool:
        """Aplica efecto de desenfoque/acrílico detrás de la ventana si el SO lo soporta."""
        ...

    def set_dpi_awareness(self) -> bool:
        """Configura el soporte de alta resolución (Per-Monitor DPI Awareness)."""
        ...

    def request_permissions(self) -> dict[str, bool]:
        """Comprueba y solicita permisos del sistema (cámara, micro, pantalla)."""
        ...
