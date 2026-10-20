# Soporte de Plataformas y Limitaciones

## Niveles de Soporte

| Plataforma | Soporte | Exclusión de Ventanas Propias | Backend de Captura | Notas |
|---|---|---|---|---|
| **Windows 11 / 10 (2004+)** | Completo (Tier 1) | `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` | `dxcam` (DXGI) / `mss` | Plataforma prioritaria de desarrollo |
| **macOS (13+)** | Completo (Tier 2) | ScreenCaptureKit `excludingWindows` | `ScreenCaptureKit` / `mss` | Requiere permisos de sistema |
| **Linux (X11)** | Parcial (Tier 3) | No soportado por el servidor X11 | `mss` + XFixes | Se recomienda colocar teleprompter fuera del área o en 2do monitor |
| **Linux (Wayland)** | Experimental | No soportado | Portal ScreenCast / PipeWire | Sin atajos globales directos |

## Detalles de Exclusión en Windows 11

Windows 10 versión 2004 (Build 19041) introdujo `WDA_EXCLUDEFROMCAPTURE = 0x00000011`.
Esta llamada informa al subsistema DWM / DXGI que la ventana específica debe omitirse en Desktop Duplication y capturas de pantalla, mostrando el contenido subyacente.
RecordMe aplica esta afinidad inmediatamente después de inicializar cada ventana y overlay auxiliar.
