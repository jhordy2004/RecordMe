"""Renderizado y composición de la capa de cámara con formas, bordes y recorte cover."""

import logging

import cv2
import numpy as np
import numpy.typing as npt

from recordme.core.render_state import CameraLayout

logger = logging.getLogger(__name__)


class CameraLayer:
    """Aplica la cámara como burbuja (círculo, rectángulo redondeado o rectángulo) sobre el frame."""

    def __init__(self) -> None:
        self._cached_mask_key: tuple[str, int, int, int] | None = None
        self._cached_mask: npt.NDArray[np.float32] | None = None
        self._bg_subtractor: cv2.BackgroundSubtractorMOG2 | None = None
        self._cached_bg_path: str | None = None
        self._cached_bg_img: npt.NDArray[np.uint8] | None = None

    def _apply_virtual_background(
        self,
        cam_frame: npt.NDArray[np.uint8],
        bg_path: str,
    ) -> npt.NDArray[np.uint8]:
        """Reemplaza el fondo de la cámara por la imagen seleccionada."""
        try:
            if self._cached_bg_path != bg_path or self._cached_bg_img is None:
                loaded = cv2.imread(bg_path)
                if loaded is not None:
                    self._cached_bg_path = bg_path
                    self._cached_bg_img = np.asarray(loaded, dtype=np.uint8)
                else:
                    return cam_frame

            if self._cached_bg_img is None:
                return cam_frame

            h, w = cam_frame.shape[:2]
            bg_resized = np.asarray(cv2.resize(self._cached_bg_img, (w, h), interpolation=cv2.INTER_LINEAR), dtype=np.uint8)

            if self._bg_subtractor is None:
                self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
                    history=300,
                    varThreshold=25,
                    detectShadows=False,
                )

            fg_mask = self._bg_subtractor.apply(cam_frame)
            # Suavizado de bordes del sujeto
            fg_mask = cv2.GaussianBlur(fg_mask, (11, 11), 0)
            alpha = (fg_mask.astype(np.float32) / 255.0)[:, :, np.newaxis]

            composed = (cam_frame.astype(np.float32) * alpha + bg_resized.astype(np.float32) * (1.0 - alpha)).astype(np.uint8)
            return composed
        except Exception as e:
            logger.debug("Error aplicando fondo virtual: %s", e)
            return cam_frame

    def render(
        self,
        base_frame: npt.NDArray[np.uint8],
        cam_frame: npt.NDArray[np.uint8],
        layout: CameraLayout,
    ) -> npt.NDArray[np.uint8]:
        """Superpone el frame de la cámara sobre base_frame según el layout indicado."""
        if not layout.enabled or cam_frame is None or cam_frame.size == 0:
            return base_frame

        base_h, base_w = base_frame.shape[:2]

        # Calcular tamaño en píxeles según el porcentaje del ancho de salida
        size_pct = max(10, min(layout.size_pct, 50)) / 100.0
        bubble_w = int(base_w * size_pct)
        # Para círculo o cuadrado es 1:1, para rectangulares puede variar
        bubble_h = bubble_w if layout.shape in ("circle", "rounded_rect") else int(bubble_w * 9 / 16)

        # Dimensiones pares
        bubble_w = bubble_w if bubble_w % 2 == 0 else bubble_w - 1
        bubble_h = bubble_h if bubble_h % 2 == 0 else bubble_h - 1
        if bubble_w < 10 or bubble_h < 10:
            return base_frame

        # Calcular centro y coordenadas de inserción
        center_x = int(layout.center_norm_x * base_w)
        center_y = int(layout.center_norm_y * base_h)

        left = center_x - bubble_w // 2
        top = center_y - bubble_h // 2

        # Clampear a los límites del frame de salida
        left = max(0, min(left, base_w - bubble_w))
        top = max(0, min(top, base_h - bubble_h))
        right = left + bubble_w
        bottom = top + bubble_h

        # 1. Recorte "cover" centrado de la cámara para no deformar relación de aspecto
        cam_h, cam_w = cam_frame.shape[:2]
        cam_target_ratio = bubble_w / bubble_h
        cam_current_ratio = cam_w / cam_h

        if cam_current_ratio > cam_target_ratio:
            # La cámara es más ancha: recortar lados
            new_w = int(cam_h * cam_target_ratio)
            offset = (cam_w - new_w) // 2
            cropped_cam = cam_frame[:, offset : offset + new_w]
        else:
            # La cámara es más alta: recortar arriba/abajo
            new_h = int(cam_w / cam_target_ratio)
            offset = (cam_h - new_h) // 2
            cropped_cam = cam_frame[offset : offset + new_h, :]

        # Redimensionar al tamaño final de la burbuja
        resized_cam: npt.NDArray[np.uint8] = np.asarray(
            cv2.resize(cropped_cam, (bubble_w, bubble_h), interpolation=cv2.INTER_LINEAR),
            dtype=np.uint8,
        )

        # 1.5. Aplicar fondo virtual si está configurado
        if layout.virtual_bg_image:
            resized_cam = self._apply_virtual_background(resized_cam, layout.virtual_bg_image)

        # 2. Obtener o generar máscara con antialiasing
        mask = self._get_mask(layout.shape, bubble_w, bubble_h)

        # 3. Dibujar borde si está activado
        if layout.border_enabled and layout.border_width > 0:
            self._draw_border(resized_cam, layout.shape, bubble_w, bubble_h, layout.border_width, layout.border_color)

        # 4. Superponer en el frame base usando la máscara alfa
        roi = base_frame[top:bottom, left:right]
        mask_3d = np.repeat(mask[:, :, np.newaxis], 3, axis=2)

        # Mezcla alfa: roi * (1 - mask) + resized_cam * mask
        blended = (roi.astype(np.float32) * (1.0 - mask_3d) + resized_cam.astype(np.float32) * mask_3d).astype(np.uint8)
        base_frame[top:bottom, left:right] = blended

        # 5. Dibujar nombre opcional si está activado
        if layout.name_enabled and layout.name_text:
            self._draw_name(base_frame, layout.name_text, left, top, bubble_w, bubble_h, layout.name_position)

        return base_frame

    def _get_mask(self, shape: str, width: int, height: int) -> npt.NDArray[np.float32]:
        """Genera una máscara flotante [0.0, 1.0] con antialiasing para la forma indicada."""
        mask_key = (shape, width, height, 0)
        if self._cached_mask_key == mask_key and self._cached_mask is not None:
            return self._cached_mask

        # Generar a 2x supersampling para antialiasing perfecto
        scale = 2
        sw = width * scale
        sh = height * scale
        hi_mask = np.zeros((sh, sw), dtype=np.uint8)

        if shape == "circle":
            center = (sw // 2, sh // 2)
            radius = min(sw, sh) // 2 - 1
            cv2.circle(hi_mask, center, radius, 255, -1, cv2.LINE_AA)
        elif shape == "rounded_rect":
            radius = int(min(sw, sh) * 0.15)
            # Dibujar rectángulos interior y esquinas redondeadas
            cv2.rectangle(hi_mask, (radius, 0), (sw - radius, sh), 255, -1)
            cv2.rectangle(hi_mask, (0, radius), (sw, sh - radius), 255, -1)
            cv2.circle(hi_mask, (radius, radius), radius, 255, -1, cv2.LINE_AA)
            cv2.circle(hi_mask, (sw - radius, radius), radius, 255, -1, cv2.LINE_AA)
            cv2.circle(hi_mask, (radius, sh - radius), radius, 255, -1, cv2.LINE_AA)
            cv2.circle(hi_mask, (sw - radius, sh - radius), radius, 255, -1, cv2.LINE_AA)
        else:
            # Rectángulo completo
            hi_mask.fill(255)

        # Reducir a resolución original con interpolación de área (antialiasing)
        mask = cv2.resize(hi_mask, (width, height), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

        self._cached_mask = mask
        self._cached_mask_key = mask_key
        return mask

    def _draw_border(
        self,
        image: npt.NDArray[np.uint8],
        shape: str,
        width: int,
        height: int,
        border_width: int,
        border_hex_color: str,
    ) -> None:
        """Dibuja el borde con antialiasing sobre la imagen recortada."""
        color_bgr = self._hex_to_bgr(border_hex_color)
        bw = max(1, border_width)

        if shape == "circle":
            center = (width // 2, height // 2)
            radius = min(width, height) // 2 - bw // 2 - 1
            cv2.circle(image, center, radius, color_bgr, bw, cv2.LINE_AA)
        elif shape == "rounded_rect":
            radius = int(min(width, height) * 0.15)
            # Bordes redondeados simplificados
            cv2.rectangle(image, (bw // 2, bw // 2), (width - bw // 2, height - bw // 2), color_bgr, bw, cv2.LINE_AA)
        else:
            cv2.rectangle(image, (0, 0), (width - 1, height - 1), color_bgr, bw)

    def _draw_name(
        self,
        frame: npt.NDArray[np.uint8],
        text: str,
        cam_left: int,
        cam_top: int,
        cam_w: int,
        cam_h: int,
        position: str,
    ) -> None:
        """Dibuja la píldora semitransparente con efecto blur suave y texto blanco en la esquina inferior izquierda."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = max(0.4, min(cam_w, cam_h) / 360.0)
        thickness = 1
        text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)

        pill_w = text_size[0] + 16
        pill_h = text_size[1] + 10

        # Ubicar en la parte inferior izquierda de la cámara
        pill_x = cam_left + 10
        pill_y = cam_top + cam_h - pill_h - 10

        pill_x = max(0, min(pill_x, frame.shape[1] - pill_w))
        pill_y = max(0, min(pill_y, frame.shape[0] - pill_h))

        # Dibujar fondo oscuro con efecto blur suave y texto blanco
        roi = frame[pill_y : pill_y + pill_h, pill_x : pill_x + pill_w]
        if roi.shape[0] == pill_h and roi.shape[1] == pill_w:
            blurred_roi = cv2.GaussianBlur(roi, (15, 15), 0)
            dark_bg = np.full_like(roi, (20, 20, 20))
            blended_roi = cv2.addWeighted(dark_bg, 0.70, blurred_roi, 0.30, 0)
            frame[pill_y : pill_y + pill_h, pill_x : pill_x + pill_w] = blended_roi
            # Texto blanco nítido
            text_x = pill_x + 8
            text_y = pill_y + pill_h - 6
            cv2.putText(frame, text, (text_x, text_y), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

    def _hex_to_bgr(self, hex_str: str) -> tuple[int, int, int]:
        """Convierte código hexadecimal '#RRGGBB' a tupla (B, G, R)."""
        hex_clean = hex_str.lstrip("#")
        if len(hex_clean) != 6:
            return (255, 255, 255)
        r = int(hex_clean[0:2], 16)
        g = int(hex_clean[2:4], 16)
        b = int(hex_clean[4:6], 16)
        return (b, g, r)
