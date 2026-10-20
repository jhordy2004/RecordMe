# RecordMe (Presenta)

Grabador de pantalla con cámara, zoom en vivo, censura y teleprompter.
Inspirado en la facilidad de uso de la Herramienta de Recortes de Windows, pero enfocado en creadores de video, docentes y expositores.

## Características Principales

1. **Selección de Área Flexible**: Elige pantalla completa o cualquier región arbitraria.
2. **Cámara Flotante**: En recuadro circular o rectangular, reposicionable en directo sin alterar el contenido grabado.
3. **Zoom en Vivo**: Transiciones fluidas a regiones de interés o siguiendo el cursor.
4. **Censura en Tiempo Real**: Aplica blur gaussiano, pixelado o máscaras opacas sobre datos confidenciales antes de codificar.
5. **Teleprompter Integrado Invisible**: Panel flotante con avance automático de texto por WPM, blur de fondo y **excluido de la grabación**.
6. **Controles Excluidos**: La barra de herramientas y elementos auxiliares nunca se filtran en el video final.
7. **100% Offline**: Sin telemetría ni conexión a la red.

## Requisitos de Entorno de Desarrollo

- Windows 11 / 10 (Build 19041+)
- Python 3.11 x64
- FFmpeg (incluido automáticamente vía `imageio-ffmpeg` o disponible en PATH)

### Instalación

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### Ejecución

```powershell
python -m recordme
```
