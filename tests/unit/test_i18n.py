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


def test_detect_system_language_fallbacks(monkeypatch) -> None:
    """Verifica que cualquier idioma del SO no soportado devuelva inglés ('en') por defecto."""
    import recordme.utils.i18n as i18n_mod

    # Simular que Windows API falla
    monkeypatch.setattr(i18n_mod.ctypes, "windll", None)

    # Simular idioma no soportado (ej. Francés 'fr_FR')
    class MockLocale:
        @staticmethod
        def system():
            class SystemLoc:
                @staticmethod
                def uiLanguages():  # noqa: N802
                    return ["fr-FR", "fr"]

                @staticmethod
                def name():
                    return "fr_FR"

            return SystemLoc()

    monkeypatch.setattr(i18n_mod, "QLocale", MockLocale)
    assert i18n_mod.detect_system_language() == "en"

    # Simular Chino
    class MockLocaleZh:
        @staticmethod
        def system():
            class SystemLoc:
                @staticmethod
                def uiLanguages():  # noqa: N802
                    return ["zh-CN", "zh"]

                @staticmethod
                def name():
                    return "zh_CN"

            return SystemLoc()

    monkeypatch.setattr(i18n_mod, "QLocale", MockLocaleZh)
    assert i18n_mod.detect_system_language() == "zh"

    # Simular Español
    class MockLocaleEs:
        @staticmethod
        def system():
            class SystemLoc:
                @staticmethod
                def uiLanguages():  # noqa: N802
                    return ["es-ES", "es"]

                @staticmethod
                def name():
                    return "es_ES"

            return SystemLoc()

    monkeypatch.setattr(i18n_mod, "QLocale", MockLocaleEs)
    assert i18n_mod.detect_system_language() == "es"

