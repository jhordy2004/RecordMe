# Registro de Cambios (CHANGELOG)

## [Fase 0: Cimientos] - 2026-10-20

### Agregado
- Estructura modular del proyecto `recordme` con soporte para Python 3.11.
- Configuración centralizada de metadatos y nombre del proyecto (`constants.py` con `APP_NAME = "RecordMe"`).
- Sistema de rutas multiplataforma con `platformdirs` para configuración, logs, datos y temporales.
- Sistema de configuración persistente `settings.py` tolerante a fallos y archivos JSON corruptos.
- Máquina de estados para sesión de grabación (`SessionState` y `SessionManager`) con validación de transiciones.
- Abstracción de protocolos de captura (`CaptureBackend`) y servicios de sistema operativo (`PlatformServices`).
- Implementación Win32 de Per-Monitor DPI Awareness y exclusión de ventanas de captura (`SetWindowDisplayAffinity`).
- Interfaz Qt inicial con tema oscuro uniforme y ventana de verificación (`app.py`).
- Suite de pruebas unitarias para configuración, geometría y máquina de estados.

---

### Comando para prueba manual
```powershell
.\.venv\Scripts\python -m recordme
```
