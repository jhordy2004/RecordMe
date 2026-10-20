"""Detección y consulta de dispositivos de audio con sounddevice."""

import logging
from dataclasses import dataclass
from typing import Any

import sounddevice as sd

logger = logging.getLogger(__name__)


@dataclass
class AudioDeviceInfo:
    """Información de un dispositivo de entrada de audio."""
    index: int
    name: str
    max_input_channels: int
    default_samplerate: float


def list_input_devices() -> list[AudioDeviceInfo]:
    """Lista todos los dispositivos de captura de audio disponibles en el sistema."""
    devices: list[AudioDeviceInfo] = []
    try:
        raw_devices: list[dict[str, Any]] = sd.query_devices()
        for idx, dev in enumerate(raw_devices):
            channels = int(dev.get("max_input_channels", 0))
            if channels > 0:
                devices.append(
                    AudioDeviceInfo(
                        index=idx,
                        name=str(dev.get("name", f"Micrófono {idx}")),
                        max_input_channels=channels,
                        default_samplerate=float(dev.get("default_samplerate", 48000)),
                    )
                )
    except Exception as e:
        logger.warning("Error consultando dispositivos de audio: %s", e)

    return devices
