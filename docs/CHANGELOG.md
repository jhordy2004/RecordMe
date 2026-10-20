# Registro de Cambios (CHANGELOG)

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
