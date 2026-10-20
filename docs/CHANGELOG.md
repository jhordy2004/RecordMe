# Registro de Cambios (CHANGELOG)

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
- **Pruebas Automatizadas**:
  - `tests/unit/test_camera_layer.py`: pruebas de renderizado de máscaras, superposición de colores y formas.
  - `tests/ui/test_camera_preview.py`: pruebas de interacción, recepción de frames y señales de layout.

---

### Comando para probar manualmente la Fase 2
```powershell
.\.venv\Scripts\python -m recordme
```
1. Verás aparecer el botón **Cámara: Off** en la barra de herramientas.
2. Haz clic en **Cámara**: se activará pasando a **Cámara: On** y aparecerá la burbuja flotante con tu imagen.
3. Arrastra la burbuja con el ratón para ubicarla en cualquier esquina de tu pantalla.
4. Gira la rueda del ratón sobre la burbuja para agrandarla o achicarla en vivo.
5. Pulsa **Grabar**: la burbuja de la cámara se grabará perfectamente en la posición elegida sin que se vea la ventana de la barra ni la ventana de preview nativa duplicada.
6. Mientras grabas, mueve la burbuja a otra posición o desactiva la cámara con el botón de la barra.
7. Pulsa **Detener**: reproduce el video MP4 resultante y comprueba que la cámara se grabó en sincronía, con su forma circular y borde nítido.

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
- **Pruebas Automatizadas**:
  - `test_magenta_exclusion.py`: comprobación de no intrusión de ventanas excluidas.
  - `test_synthetic_recording.py`: generación de video sintético y audio senoidal 440 Hz a MP4.
  - `test_recording_controller.py`: ciclo de vida completo de grabación con pausa y reanudación.

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
