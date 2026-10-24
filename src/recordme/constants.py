"""Constantes globales del proyecto RecordMe."""

from typing import Final

# Nombre de la aplicación (centralizado en una sola constante)
APP_NAME: Final[str] = "RecordMe"
APP_DISPLAY_NAME: Final[str] = "RecordMe"
APP_VERSION: Final[str] = "0.1.1"

# Identificador de organización para directorios de sistema
ORGANIZATION_NAME: Final[str] = "RecordMe"

# Constantes de video por defecto
DEFAULT_FPS: Final[int] = 30
DEFAULT_AUDIO_SAMPLE_RATE: Final[int] = 48000
DEFAULT_AUDIO_CHANNELS: Final[int] = 2

# Exclusión de captura en Windows (Windows 10 2004+ Build 19041+)
WDA_NONE: Final[int] = 0x00000000
WDA_MONITOR: Final[int] = 0x00000001
WDA_EXCLUDEFROMCAPTURE: Final[int] = 0x00000011
