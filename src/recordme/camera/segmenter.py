"""Segmentador de personas para reemplazo de fondo virtual en tiempo real (estilo Zoom)."""

import logging
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt

logger = logging.getLogger(__name__)


class CameraSegmenter:
    """Aplica segmentación de personas y sustitución de fondo virtual usando redes neuronales DNN."""

    _instance: "CameraSegmenter | None" = None

    def __init__(self) -> None:
        self._net: cv2.dnn.Net | None = None
        self._cached_bg_path: str | None = None
        self._cached_bg_img: npt.NDArray[np.uint8] | None = None
        self._init_model()

    @classmethod
    def get_instance(cls) -> "CameraSegmenter":
        """Singleton para reutilizar el modelo compilado en memoria."""
        if cls._instance is None:
            cls._instance = CameraSegmenter()
        return cls._instance

    def _init_model(self) -> None:
        """Carga el modelo ONNX de segmentación de selfie."""
        try:
            model_path = Path(__file__).resolve().parent.parent / "resources" / "selfie_segmentation.onnx"
            if model_path.exists():
                self._net = cv2.dnn.readNetFromONNX(str(model_path))
                # Optimizar para CPU
                self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                logger.info("Modelo de segmentación de fondo cargado exitosamente: %s", model_path.name)
            else:
                logger.warning("No se encontró el modelo de segmentación en: %s", model_path)
        except Exception as e:
            logger.error("Error inicializando modelo de segmentación: %s", e)
            self._net = None

    def apply_background(
        self,
        cam_frame: npt.NDArray[np.uint8],
        bg_path_or_img: str | npt.NDArray[np.uint8],
    ) -> npt.NDArray[np.uint8]:
        """Reemplaza el fondo de `cam_frame` con la imagen de fondo proporcionada."""
        if cam_frame is None or cam_frame.size == 0:
            return cam_frame

        # Cargar o usar la imagen de fondo
        bg_img: npt.NDArray[np.uint8] | None = None
        if isinstance(bg_path_or_img, str):
            if bg_path_or_img != self._cached_bg_path or self._cached_bg_img is None:
                loaded = cv2.imread(bg_path_or_img)
                if loaded is not None:
                    self._cached_bg_path = bg_path_or_img
                    self._cached_bg_img = np.asarray(loaded, dtype=np.uint8)
                else:
                    return cam_frame
            bg_img = self._cached_bg_img
        elif isinstance(bg_path_or_img, np.ndarray):
            bg_img = bg_path_or_img

        if bg_img is None:
            return cam_frame

        h, w = cam_frame.shape[:2]

        # Si el modelo DNN no está disponible, devolver frame original
        if self._net is None:
            return cam_frame

        try:
            # 1. Preprocesar para el modelo (256x256, escala [0, 1], RGB)
            blob = cv2.dnn.blobFromImage(
                cam_frame,
                scalefactor=1.0 / 255.0,
                size=(256, 256),
                swapRB=True,
                crop=False,
            )
            self._net.setInput(blob)
            out = self._net.forward()

            # 2. Máscara de probabilidad de primer plano (sujeto)
            prob_map = out[0, 0]
            mask = cv2.resize(prob_map, (w, h), interpolation=cv2.INTER_LINEAR)

            # Umbral suave y desenfoque para transiciones naturales
            mask = np.clip((mask - 0.3) / 0.4, 0.0, 1.0)
            mask = cv2.GaussianBlur(mask, (7, 7), 0)

            # 3. Redimensionar fondo al tamaño del frame de la cámara
            if bg_img.shape[0] != h or bg_img.shape[1] != w:
                bg_resized = cv2.resize(bg_img, (w, h), interpolation=cv2.INTER_LINEAR)
            else:
                bg_resized = bg_img

            # 4. Mezcla alfa: cam * alpha + bg * (1 - alpha)
            alpha_3d = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
            blended: npt.NDArray[np.uint8] = np.asarray(
                cam_frame.astype(np.float32) * alpha_3d
                + bg_resized.astype(np.float32) * (1.0 - alpha_3d),
                dtype=np.uint8,
            )

            return blended
        except Exception as e:
            logger.debug("Error procesando segmentación: %s", e)
            return cam_frame
