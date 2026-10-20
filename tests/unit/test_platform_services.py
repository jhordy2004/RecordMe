"""Pruebas unitarias para servicios de plataforma."""

from recordme.platform_services.factory import get_platform_services


def test_platform_services_instantiation() -> None:
    """Verifica que el servicio de plataforma se instancie de acuerdo al SO."""
    services = get_platform_services()
    assert services is not None
    perms = services.request_permissions()
    assert isinstance(perms, dict)
    assert "screen_capture" in perms
