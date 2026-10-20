# Arquitectura de RecordMe (Presenta)

## Principio Central: Compositor Propio

RecordMe no graba la pantalla de forma pasiva o directa. En cada ciclo de reloj se ejecuta un pipeline de composición determinista:

```
[Captura Pantalla Nativa] (dxcam DXGI / mss)
   │
   ▼
[Recorte a Región Seleccionada] (coordenadas físicas)
   │
   ▼
[Censura en Tiempo Real] (Blur Gaussiano / Pixelado / Sólido)
   │
   ▼
[Zoom Dinámico] (Interpolación continua con amortiguamiento tau)
   │
   ▼
[Capa de Cámara] (Burbuja circular/rectangular con antialiasing)
   │
   ▼
[Capa de Cursor] (Icono real con escalado DPI)
   │
   ▼
[Escritura a FFmpeg stdin] (BGR24 rawvideo -> MKV temporal)
```

## Modelo de Concurrencia y Paso de Mensajes

1. **Hilo UI (PySide6)**:
   - Controla todas las ventanas, overlays, interacciones del usuario y eventos Qt.
   - Modifica el objeto atómico `RenderState` ante cualquier cambio de zoom, censura o movimiento de cámara.

2. **Hilo de Captura de Pantalla**:
   - Captura frames a resolución nativa del monitor.
   - Almacena atómicamente el puntero al último frame (`latest_frame`).

3. **Hilo de Cámara**:
   - Lee frames de OpenCV `VideoCapture`.
   - Aplica opcionalmente segmentación de fondo en hilo secundario.
   - Deja disponible el último frame procesado.

4. **Hilo del Compositor**:
   - Reloj de frames de alta precisión basado en `time.perf_counter()`.
   - Consulta el último snapshot de `RenderState`.
   - Ejecuta las transformaciones de imagen sobre búferes preasignados.
   - Empuja el frame final a la cola de salida de video.

5. **Hilo de Grabación de Audio**:
   - `sounddevice.InputStream` alimentando un archivo temporal WAV vía `soundfile`.
   - Mantiene sincronía grabando silencio durante pausas.

6. **Muxer Final**:
   - Concatena y sincroniza el MKV y el WAV aplicando `-itsoffset` con el delta medido al inicio.
