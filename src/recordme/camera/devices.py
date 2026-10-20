"""Detección y enumeración de cámaras de video del sistema."""

import logging
from dataclasses import dataclass

import cv2
from PySide6.QtMultimedia import QMediaDevices

logger = logging.getLogger(__name__)


@dataclass
class CameraDeviceInfo:
    """Información de un dispositivo de cámara."""
    index: int
    name: str
    id: str


def list_camera_devices() -> list[CameraDeviceInfo]:
    """Lista las cámaras disponibles en el sistema usando QMediaDevices o sondeo de OpenCV."""
    devices: list[CameraDeviceInfo] = []

    # 1. Intentar con QMediaDevices (Qt 6)
    try:
        qt_cameras = QMediaDevices.videoInputs()
        if qt_cameras:
            for idx, cam in enumerate(qt_cameras):
                devices.append(
                    CameraDeviceInfo(
                        index=idx,
                        name=cam.description() or f"Cámara {idx}",
                        id=str(cam.id()),
                    )
                )
            if devices:
                logger.info("Detectadas %d cámaras vía QMediaDevices.", len(devices))
                return devices
    except Exception as e:
        logger.debug("Error listando cámaras con QMediaDevices: %s", e)

    # 2. Fallback: Sondeo rápido con OpenCV (hasta 4 índices)
    for idx in range(4):
        try:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if cap.isOpened():
                devices.append(
                    CameraDeviceInfo(
                        index=idx,
                        name=f"Cámara {idx}",
                        id=f"cv2_{idx}",
                    )
                )
                cap.release()
        except Exception:
            pass

    logger.info("Detectadas %d cámaras vía sondeo OpenCV.", len(devices))
    return devices
