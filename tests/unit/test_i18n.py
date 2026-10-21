"""Pruebas unitarias para el sistema de I18n y detección de idioma."""

from recordme.utils.i18n import detect_system_language, get_current_language, init_language, tr


def test_i18n_language_switching_and_translation() -> None:
    """Verifica que las traducciones se adapten a español, chino e inglés."""
    # Español
    init_language("es")
    assert get_current_language() == "es"
    assert tr("tb_record") == "Grabar"
    assert tr("tb_area") == "Área"

    # Inglés (por defecto si no es español ni chino)
    init_language("en")
    assert get_current_language() == "en"
    assert tr("tb_record") == "Record"
    assert tr("tb_area") == "Area"

    # Chino
    init_language("zh")
    assert get_current_language() == "zh"
    assert tr("tb_record") == "录制"
    assert tr("tb_area") == "区域"

    # Fallback para idioma desconocido -> 'en'
    detected = detect_system_language()
    assert detected in ("es", "zh", "en")

    # Restaurar a español para el resto de tests
    init_language("es")
