"""Configuración global de pruebas para pytest."""

import pytest

from recordme.utils.i18n import init_language


@pytest.fixture(autouse=True)
def default_spanish_locale_for_tests():
    """Asegura que el entorno de tests use español por defecto para consistencia con assertions de UI existentes."""
    init_language("es")
    yield
    init_language("es")
