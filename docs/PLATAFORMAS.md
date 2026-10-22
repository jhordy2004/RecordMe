# Soporte de Plataformas, Limitaciones y Empaquetado

## Niveles de Soporte

| Plataforma | Soporte | Exclusión de Ventanas Propias | Backend de Captura | Empaquetado Oficial | Notas |
|---|---|---|---|---|---|
| **Windows 11 / 10 (2004+)** | Completo (Tier 1) | `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` | `dxcam` (DXGI) / `mss` | PyInstaller (`--onefile` / `--onedir`) + Inno Setup | Plataforma prioritaria de desarrollo |
| **macOS (13+ Ventura / Sonoma)** | Completo (Tier 2) | ScreenCaptureKit `SCContentFilter(excludingWindows:)` | `MacOSScreenCaptureKitBackend` / `mss` | Bundle `.app` y `.dmg` montable | Requiere permisos de Grabación de pantalla y Accesibilidad |
| **Linux (X11)** | Completo con Estrategia (Tier 3) | Estrategia de Colocación Fuera del Área | `LinuxX11CaptureBackend` (XShm / `mss`) | `AppImage` standalone | Reposicionamiento automático de controles fuera del área |
| **Linux (Wayland)** | Experimental | Estrategia de Colocación Fuera del Área | Portal ScreenCast / XWayland | `AppImage` | Se recomienda sesión X11 o 2do monitor |

---

## Detalles por Plataforma

### 1. Windows 11 / 10 (2004+)
- **Exclusión**: `WDA_EXCLUDEFROMCAPTURE = 0x00000011`. Informa a DWM y DXGI Desktop Duplication que la ventana debe omitirse en la captura.
- **Empaquetado**:
  - `Release/RecordMe.exe` (ejecutable portátil `--onefile`).
  - `Release/RecordMe-v0.1.0-windows-x64.zip` (distribución `--onedir` lista para descomprimir y usar).
  - `Release/RecordMe_Setup_v0.1.0.exe` (instalador profesional Inno Setup con accesos directos y desinstalador limpio).
- **Cero dependencias**: No requiere Python ni FFmpeg instalados; todo está autocontenido.

### 2. macOS (13+ Ventura / Sonoma)
- **Exclusión**: ScreenCaptureKit (`SCContentFilter`). Se registran los `CGWindowID` de la barra flotante, marco de región y teleprompter. El filtro excluye estas ventanas a nivel de compositor gráfico de Apple.
- **Permisos requeridos**:
  1. *Grabación de pantalla*: Otorgado en *Ajustes del Sistema > Privacidad y Seguridad > Grabación de Pantalla*.
  2. *Accesibilidad*: Necesario para la captura de atajos globales (`pynput`) en segundo plano.
  3. *Cámara y Micrófono*: Solicitados automáticamente al activar dichas funciones.
- **Empaquetado**:
  - Script `scripts/build_macos.sh`: genera `RecordMe.app` firmado ad-hoc y empaquetado en imagen `RecordMe.dmg`.

### 3. Linux (X11 y Wayland)
- **Estrategia de Exclusión**: Dado que el protocolo X11 no dispone de un flag equivalente a `WDA_EXCLUDEFROMCAPTURE`, RecordMe implementa la **Estrategia de Colocación Fuera del Área** (`reposition_outside_region`).
  - Al seleccionar un área personalizada, la barra y el teleprompter se sitúan dinámicamente arriba o abajo de las coordenadas grabadas.
  - Si se graba a pantalla completa, la interfaz avisa al usuario para que ubique los controles en un segundo monitor o use un área de pantalla.
- **Empaquetado**:
  - Script `scripts/build_linux.sh`: genera el paquete portátil `RecordMe-x86_64.AppImage` con su archivo `.desktop` e icono de alta resolución.
