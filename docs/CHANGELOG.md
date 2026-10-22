# Registro de Cambios (CHANGELOG)

## [Fase 6: Empaquetado Windows (PyInstaller + Inno Setup)] - 2026-10-22

### Agregado
- **Compilación PyInstaller Dual (OneFile y OneDir)**:
  - Archivo `recordme.spec` para bundling automático de todas las dependencias nativas (PySide6, OpenCV, DXCam, PortAudio/sounddevice, imageio_ffmpeg, pynput, docx).
  - Integración del ejecutable FFmpeg dentro del paquete congelado mediante `ffmpeg_locator.py` resiliente a rutas `_MEIPASS`.
  - Iconos multirresolución (16x16 a 256x256) embebidos y fijados en la barra de tareas de Windows 11.
  - Modelo ONNX `selfie_segmentation.onnx` embebido para fondo virtual en tiempo real sin conexión a internet.
  - **Ejecutable OneFile Portátil (`Release/RecordMe.exe`)**: Doble clic y ejecución inmediata sin instalar nada.
  - **Distribución Zipeada (`Release/RecordMe-v0.1.0-windows-x64.zip`)**: Paquete portable con arranque instantáneo.
- **Instalador Profesional Inno Setup 6 (`installer.iss`)**:
  - Compilación automática con `ISCC.exe` generando `Release/RecordMe_Setup_v0.1.0.exe`.
  - Soporte multilingüe (Español / Inglés).
  - Instalación limpia por usuario (`PrivilegesRequired=lowest`), accesos directos opcionales en Escritorio y Menú Inicio, y desinstalador completo.
- **Script Orquestador de Compilación**:
  - `build_release.ps1`: Automatiza la generación de binarios, compresión ZIP, compilación de Inno Setup y cálculo de sumas de verificación SHA256, replicando en la carpeta `Release/` (y `Relase/`).

---

## [Fase 7: Soporte macOS y ScreenCaptureKit] - 2026-10-22

### Agregado
- **Servicios de Plataforma para macOS (`MacOSPlatformServices`)**:
  - Exclusión nativa de ventanas propias (barra flotante, marco de región, teleprompter) registrada mediante `CGWindowID` / `winId()`.
  - Comprobación y solicitud proactiva de permisos del sistema operativo mediante APIs Cocoa/CoreGraphics (`CGPreflightScreenCaptureAccess`, `CGRequestScreenCaptureAccess`), Accesibilidad para atajos (`AXIsProcessTrusted`) y AVFoundation para cámara/micrófono.
- **Backend de Captura ScreenCaptureKit (`MacOSScreenCaptureKitBackend`)**:
  - Flujo de captura acelerado por hardware en macOS 12.3+ / 13+ (Ventura y Sonoma).
  - Uso de filtros `SCContentFilter(display: excludingWindows: excluded_window_ids)` que omiten automáticamente las herramientas de RecordMe del video final a nivel de compositor Quartz.
  - Fallback transparente a `MSSCaptureBackend` en entornos heredados.
- **Empaquetado para macOS**:
  - Script `scripts/package_macos.sh` que genera el bundle `RecordMe.app` firmado ad-hoc con descripciones de privacidad en `Info.plist` y genera la imagen montable `RecordMe-0.1.0-macOS.dmg`.

---

## [Fase 8: Soporte Linux X11 y Wayland con Estrategia Fuera del Área] - 2026-10-22

### Agregado
- **Servicios de Plataforma para Linux (`LinuxPlatformServices`)**:
  - Detección automática del servidor gráfico (`X11` vs `Wayland` vía `XDG_SESSION_TYPE`).
  - **Estrategia de Colocación Fuera del Área (`reposition_outside_region`)**: Al no existir en X11 un análogo directo de `WDA_EXCLUDEFROMCAPTURE`, la aplicación reposiciona automáticamente la barra flotante y el teleprompter fuera del rectángulo delimitador grabado.
  - Notificaciones en la interfaz informando sobre limitaciones del servidor gráfico y recomendaciones de grabación por área o monitor secundario.
- **Backend de Captura Linux (`LinuxX11CaptureBackend`)**:
  - Captura optimizada mediante memoria compartida XShm / MSS y soporte experimental para portales Wayland.
- **Empaquetado AppImage**:
  - Script `scripts/package_linux.sh` y estructura `AppDir` con archivo `recordme.desktop` y lanzador `AppRun` para distribución como `RecordMe-0.1.0-x86_64.AppImage`.

---

## [Fase 3: Teleprompter Invisible y Editor] - 2026-10-20

### Agregado
- **Panel Flotante de Teleprompter (`TeleprompterWidget`)**:
  - Panel angosto (60% de pantalla por defecto) de 1 a 3 líneas visibles sin ocupar toda la pantalla.
  - Fondo oscuro translúcido con desenfoque nativo (Acrylic/Mica) y letra blanca de alto contraste con resaltado de la línea central.
  - **Scroll Continuo Subpíxel**: Avance fluido gobernado por `time.perf_counter()` y WPM exacto (dentro del ±3% de tolerancia probado mediante `test_teleprompter_wpm_timing_calculation`).
  - Word-wrap automático de párrafos calculado mediante `QFontMetrics`.
  - **100% Invisible en el Video**: Excluido de la grabación mediante `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`.
  - Sincronización automática de avance/pausa al iniciar, pausar o reanudar la grabación.
  - Ajuste manual interactivo con rueda del ratón y libre reposicionamiento arrastrando por la pantalla.
- **Editor Completo de Guiones (`TeleprompterEditorDialog`)**:
  - Área de edición amplia para redactar o pegar guiones completos.
  - Botones para abrir y guardar archivos `.txt` en la carpeta de guiones del usuario.
  - Contador en tiempo real de palabras y estimación de duración en minutos y segundos según la velocidad configurada.
  - Deslizadores y controles numéricos para velocidad WPM (40–300), tamaño de fuente (18–64 px), líneas visibles (1–3) y porcentaje de opacidad del fondo.
  - Botón **Probar Teleprompter** para calibrar la velocidad en vivo antes de iniciar la sesión de grabación.
- **Control Integrado en Barra**:
  - Botón **Teleprompter** en la barra flotante para acceder inmediatamente al editor y activar el prompter.
- **Pruebas Automatizadas**:
  - `tests/unit/test_teleprompter_math.py`: verificación de precisión de avance temporal y tolerancia WPM.
  - `tests/ui/test_teleprompter.py`: ciclo de vida del widget, scroll, pausa/reanudación y editor de texto.

---

### Comando para probar manualmente la Fase 3
```powershell
.\.venv\Scripts\python -m recordme
```
1. En la barra flotante, pulsa el botón **Teleprompter**.
2. Se abrirá el **Editor de Teleprompter**:
   - Pega tu guion o escribe unas frases.
   - Observa cómo se calcula el número de palabras y el tiempo estimado en minutos/segundos.
   - Ajusta los deslizadores de velocidad (WPM), tamaño de letra y líneas visibles.
3. Haz clic en **Probar Teleprompter**: aparecerá el teleprompter flotante arriba en el centro avanzando suavemente.
4. Puedes arrastrar el teleprompter con el ratón para colocarlo cerca de tu cámara web.
5. Usa la rueda del ratón sobre el teleprompter para retroceder o adelantar el texto si lo necesitas.
6. Pulsa **Grabar**: el teleprompter avanzará al ritmo de tus palabras por minuto mientras hablas a la cámara.
7. Al pulsar **Detener**, revisa el video grabado y verifica que el teleprompter **no aparece jamás** en el video final.

---

## [Fase 2: Cámara y Burbuja en Tiempo Real] - 2026-10-20

### Agregado
- **Fuente de Cámara Multihilo (`CameraSource`)**:
  - Hilo de captura dedicado mediante OpenCV `VideoCapture` (backend preferente `CAP_DSHOW` en Windows).
  - Modo espejo horizontal (`mirror=True`) con `cv2.flip`.
  - Resiliencia ante desconexión o fallos temporales sin detener la grabación de pantalla.
  - Entrega atómica del último frame BGR al compositor y sistema de callbacks para la vista previa de la UI.
- **Capa de Composición de Cámara (`CameraLayer`)**:
  - Máscaras antialiased por supersampling 2x para formas circulares, rectángulos redondeados y rectángulos estándar.
  - Recorte "cover" centrado automático que llena la forma sin deformar la relación de aspecto del sensor.
  - Bordes de color personalizables y dibujo opcional del nombre del usuario en píldora translúcida con mezcla alfa.
  - Posicionamiento normalizado (0.0 a 1.0) respecto al área de salida final.
- **Ventana Flotante de Previsualización (`CameraPreviewWidget`)**:
  - Ventana flotante sin bordes, siempre visible (`FramelessWindowHint | WindowStaysOnTopHint | Tool`).
  - **Excluida de la captura de video** (`SetWindowDisplayAffinity`), garantizando que la ventana nativa de preview no aparezca duplicada en la grabación.
  - Totalmente arrastrable por el usuario con el ratón sobre cualquier monitor.
  - Redimensionable en vivo con la rueda del ratón (`wheelEvent`), actualizando el porcentaje de tamaño (10% a 45%).
  - Cálculo y emisión en tiempo real de su posición normalizada relativa a la región grabada.
- **Control en Barra Flotante**:
  - Botón **Cámara: On / Off** interactivo en la barra de herramientas para activar o desactivar la cámara en reposo o en plena grabación.

---

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
