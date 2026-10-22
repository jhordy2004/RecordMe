# Guía de Pruebas Manuales (QA Checklist)

## Checklist por Fase

### Fase 0: Cimientos
- [ ] Ejecutar `.\.venv\Scripts\python -m recordme`.
- [ ] Verificar que la ventana aparece con el tema oscuro sin parpadeos ni deformaciones en escalados de 100%, 125% o 150%.
- [ ] Hacer clic en "Comprobar Servicios" y verificar que la exclusión de captura reporta estado OK en Windows 11.
- [ ] Verificar que se genera el archivo de log en `%LOCALAPPDATA%\RecordMe\Logs\recordme.log`.
- [ ] Verificar que la aplicación cierra limpiamente sin excepciones en consola.

### Fase 1: Núcleo de Grabación
- [ ] Selección de área: seleccionar un área arbitraria y confirmar con Enter.
- [ ] Comprobar que la barra de herramientas no se incluye en el video final (exclusión activa).
- [ ] Grabar 2 minutos hablando por el micrófono.
- [ ] Pausar por 10 segundos, reanudar y finalizar la grabación.
- [ ] Reproducir el MP4 resultante en VLC o Reproductor Multimedia de Windows: verificar audio y video en perfecta sincronía.

### Fase 6: Empaquetado Windows (PyInstaller + Inno Setup)
- [ ] En un equipo o máquina virtual con instalación limpia de Windows 11 sin Python instalado:
- [ ] Copiar `Release/RecordMe.exe` (--onefile) y ejecutarlo haciendo doble clic:
  - [ ] Verificar que arranca de inmediato con su icono en barra de tareas.
  - [ ] Verificar que graba video y audio correctamente utilizando el FFmpeg embebido.
  - [ ] Verificar que no genera ventanas de consola negras inesperadas.
- [ ] Descomprimir `Release/RecordMe-v0.1.0-windows-x64.zip` y ejecutar `RecordMe.exe`:
  - [ ] Verificar inicio instantáneo (arranque rápido sin extracción previa).
- [ ] Ejecutar `Release/RecordMe_Setup_v0.1.0.exe`:
  - [ ] Verificar asistente con logo, términos y ruta de instalación por defecto.
  - [ ] Comprobar creación de acceso directo en el Escritorio y en el Menú Inicio con su icono.
  - [ ] Lanzar RecordMe desde el acceso directo y realizar una grabación de prueba.
  - [ ] Desinstalar desde *Configuración > Aplicaciones instaladas*: verificar eliminación limpia de archivos.

### Fase 7: macOS (ScreenCaptureKit y Permisos)
- [ ] En macOS 13+ (Ventura / Sonoma):
  - [ ] Al iniciar por primera vez, verificar diálogo del sistema solicitando permisos de *Grabación de pantalla* y *Accesibilidad*.
  - [ ] Activar los permisos en *Ajustes del Sistema > Privacidad y Seguridad*.
  - [ ] Abrir el teleprompter y la barra de herramientas.
  - [ ] Grabar una sesión de 30 segundos.
  - [ ] Inspeccionar el video `.mp4`: verificar que ni la barra flotante ni el teleprompter aparecen en la grabación gracias a `SCContentFilter(excludingWindows:)`.
  - [ ] Probar atajos de teclado globales (`Alt+R`, `Alt+P`, etc.) funcionando en segundo plano.
  - [ ] Montar `RecordMe.dmg` y arrastrar `RecordMe.app` a la carpeta `/Applications`.

### Fase 8: Linux (X11 y Estrategia Fuera del Área)
- [ ] En Ubuntu / Fedora con sesión X11:
  - [ ] Ejecutar `RecordMe-x86_64.AppImage` (otorgando permisos con `chmod +x`).
  - [ ] Seleccionar un área de grabación rectangular en pantalla.
  - [ ] Verificar que la barra de herramientas y el teleprompter se mueven automáticamente **fuera** de los límites del área grabada.
  - [ ] Grabar una sesión de prueba y reproducir el video: verificar que las herramientas no se grabaron.
  - [ ] En caso de seleccionar pantalla completa, verificar que la aplicación informa sobre la limitación de exclusión nativa de X11 recomendando monitor secundario o grabación por área.
