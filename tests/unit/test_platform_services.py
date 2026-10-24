"""Pruebas unitarias para servicios de plataforma."""

from recordme.platform_services.factory import get_platform_services
from recordme.platform_services.linux import LinuxPlatformServices
from recordme.platform_services.macos import MacOSPlatformServices
from recordme.utils.geometry import Rect


def test_platform_services_instantiation() -> None:
    """Verifica que el servicio de plataforma se instancie de acuerdo al SO."""
    services = get_platform_services()
    assert services is not None
    perms = services.request_permissions()
    assert isinstance(perms, dict)
    assert "screen_capture" in perms


def test_macos_platform_services_exclusion_and_permissions() -> None:
    """Verifica que MacOSPlatformServices registre ventanas para SCContentFilter y reporte permisos."""
    macos_svc = MacOSPlatformServices()
    assert macos_svc.set_dpi_awareness() is True

    class DummyWidget:
        def winId(self):  # noqa: N802
            return 123456

        def isVisible(self):  # noqa: N802
            return True

    widget = DummyWidget()
    assert macos_svc.exclude_window_from_capture(widget) is True
    assert 123456 in macos_svc.get_excluded_window_ids()

    perms = macos_svc.request_permissions()
    assert "screen_capture" in perms
    assert "accessibility" in perms
    assert "camera" in perms


def test_linux_platform_services_reposition_outside_area() -> None:
    """Verifica la estrategia de colocación fuera del área de LinuxPlatformServices."""
    linux_svc = LinuxPlatformServices()
    assert linux_svc.has_native_window_exclusion() is False
    assert len(linux_svc.get_system_warning()) > 0

    class DummyMovableWidget:
        def __init__(self, w: int, h: int):
            self._w = w
            self._h = h
            self.x = 0
            self.y = 0

        def geometry(self):
            class Geom:
                def __init__(self, w, h):
                    self._w = w
                    self._h = h
                def width(self):
                    return self._w
                def height(self):
                    return self._h
            return Geom(self._w, self._h)

        def move(self, x: int, y: int):
            self.x = x
            self.y = y

    # Región grabada: (200, 200, 800, 400) en pantalla 1920x1080
    widget = DummyMovableWidget(300, 50)
    region = Rect(x=200, y=200, width=800, height=400)
    screen_geom = Rect(x=0, y=0, width=1920, height=1080)

    # Como hay espacio arriba (y=200 >= 50 + 10), debe colocarse arriba del área grabada
    linux_svc.reposition_outside_region(widget, region, screen_geom)
    assert widget.y == 200 - 50 - 10  # 140
    assert widget.y < region.y  # Completamente fuera del área grabada


def test_macos_screencapturekit_backend_lifecycle() -> None:
    """Verifica el ciclo de vida de MacOSScreenCaptureKitBackend (inicio, frame, parada)."""
    from recordme.capture.macos_screencapturekit import MacOSScreenCaptureKitBackend

    backend = MacOSScreenCaptureKitBackend(display_idx=0)
    region = Rect(x=0, y=0, width=800, height=600)

    success = backend.start(region, fps=30)
    assert success is True

    frame = backend.get_latest_frame()
    if frame is not None:
        assert frame.ndim == 3

    screens = backend.screens()
    assert isinstance(screens, list)
    assert len(screens) >= 1

    backend.stop()
    assert backend.get_latest_frame() is None


def test_macos_system_settings_urls() -> None:
    """Verifica que open_system_settings no falle y reconozca secciones."""
    macos_svc = MacOSPlatformServices()
    # En entornos no-darwin debe retornar limpiamente
    macos_svc.open_system_settings("screen")
    macos_svc.open_system_settings("accessibility")


def test_linux_x11_backend_lifecycle() -> None:
    """Verifica el ciclo de vida de LinuxX11CaptureBackend (inicio, frame, parada)."""
    from recordme.capture.linux_x11 import LinuxX11CaptureBackend

    backend = LinuxX11CaptureBackend(display_idx=0)
    region = Rect(x=0, y=0, width=640, height=480)

    success = backend.start(region, fps=30)
    assert success is True

    frame = backend.get_latest_frame()
    if frame is not None:
        assert frame.ndim == 3

    screens = backend.screens()
    assert isinstance(screens, list)
    assert len(screens) >= 1

    backend.stop()
    assert backend.get_latest_frame() is None



