# Registro de Cambios (CHANGELOG)

## [Fase 1: Núcleo de Grabación en Windows] - 2026-10-20

### Agregado
- **Captura de Pantalla Resiliente**:
  - Implementación con `dxcam` (DXGI Desktop Duplication acelerado por GPU).
  - Fallback automático con `mss` (Software).
  - Fallback universal de alta fidelidad `QtScreenCaptureBackend` (`QScreen.grabWindow`) con compatibilidad 100% y soporte per-monitor DPI.
- **Exclusión de Captura Nativa**:
  - Implementación de `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE = 0x00000011)` para ocultar completamente ventanas de control y overlays de la grabación.
  - Validación con prueba automatizada del magenta (`test_magenta_exclusion.py`) verificando 0 píxeles magenta en la grabación.
- **Overlay Selector de Área (`RegionSelectorOverlay`)**:
  - Trazado interactivo de rectángulos en pantalla completa.
  - Conversión precisa de coordenadas lógicas a físicas con `devicePixelRatio`.
  - Normalización forzada a dimensiones pares (`to_even`) requerida por codificadores H.264/yuv420p.
- **Pipeline de Video FFmpeg (`VideoWriter`)**:
  - Ingesta de frames BGR24 vía pipe `stdin` sin tocar disco entre frames.
  - Codificación directa a contenedor temporal `.mkv` con `libx264` y `preset veryfast`.
- **Grabador de Audio de Micrófono (`MicRecorder`)**:
  - Captura en tiempo real con `sounddevice` a 48 kHz estéreo hacia archivo temporal `.wav`.
  - Soporte de silencio continuo durante estados silenciados (mute) para preservar la sincronía A/V.
- **Compositor de Tiempo Real (`Compositor`)**:
  - Reloj de frames de microsegundos con `time.perf_counter()`.
  - Recorte dinámico al área seleccionada.
  - Duplicación de frames en caso de retardo para mantener duración absoluta del video.
- **Muxer con Compensación de Desfase (`Muxer`)**:
  - Cálculo de offset exacto entre el primer frame de video y el primer bloque de audio.
  - Muxing sin recodificación de video (`-c:v copy`) y audio AAC 160k a contenedor final `.mp4` con `+faststart`.
- **Barra de Controles Flotante (`FloatingToolbar`)**:
  - Interfaz compacta con estados: Grabar, Pausar/Reanudar, Detener, Selector de Área y Contador `mm:ss`.
  - Arrastrable y con exclusión de captura activa.
- **Pruebas Automatizadas**:
  - `test_magenta_exclusion.py`: comprobación de no intrusión de ventanas excluidas.
  - `test_synthetic_recording.py`: generación de video sintético y audio senoidal 440 Hz a MP4.
  - `test_recording_controller.py`: ciclo de vida completo de grabación con pausa y reanudación.

---

### Comando para probar manualmente la Fase 1
```powershell
.\.venv\Scripts\python -m recordme
```
1. Se abrirá la barra flotante arriba en el centro.
2. Pulsa en **Área** para dibujar un rectángulo de pantalla (o presiona Enter para pantalla completa).
3. Pulsa en **Grabar**: la barra cambiará al modo compacto con temporizador en rojo.
4. Mueve ventanas o navega por el área; la barra flotante no aparecerá en el video grabado.
5. Pulsa **Pausar** y luego **Reanudar**.
6. Pulsa **Detener**: se generará el archivo MP4 en `Videos/RecordMe` y se abrirá el cuadro de diálogo con el botón para **Abrir carpeta**.

---

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

