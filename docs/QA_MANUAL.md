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
