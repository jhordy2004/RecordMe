"""Servicio de atajos de teclado globales del sistema usando pynput con señales Qt seguras."""

import logging
from typing import Any

from pynput import keyboard
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class GlobalHotkeyService(QObject):
    """Escucha atajos de teclado globales en segundo plano y emite señales en el hilo de Qt."""

    zoom_in = Signal()
    zoom_out = Signal()
    zoom_reset = Signal()
    pan_up = Signal()
    pan_down = Signal()
    pan_left = Signal()
    pan_right = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener: keyboard.Listener | None = None
        self._pressed_keys: set[Any] = set()

    def start(self) -> bool:
        """Inicia el escuchador de teclado global."""
        try:
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
                daemon=True,
            )
            self._listener.start()
            logger.info("GlobalHotkeyService iniciado (Ctrl++, Ctrl+-, flechas).")
            return True
        except Exception as e:
            logger.warning("No se pudo iniciar GlobalHotkeyService: %s", e)
            return False

    def stop(self) -> None:
        """Detiene el escuchador global."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception as e:
                logger.debug("Error deteniendo listener: %s", e)
            finally:
                self._listener = None
        self._pressed_keys.clear()

    def _is_ctrl_pressed(self) -> bool:
        """Verifica si alguna tecla Control (izquierda o derecha) está presionada."""
        return any(
            k in self._pressed_keys
            for k in (
                keyboard.Key.ctrl,
                keyboard.Key.ctrl_l,
                keyboard.Key.ctrl_r,
            )
        )

    def _on_press(self, key: Any) -> None:
        """Manejador de pulsación de teclas."""
        self._pressed_keys.add(key)
        ctrl = self._is_ctrl_pressed()

        if not ctrl:
            return

        # 1. Zoom In (Ctrl + '+' o Ctrl + '=')
        char = getattr(key, "char", None)
        vk = getattr(key, "vk", None)

        if char in ("+", "=") or vk in (187, 107):
            logger.debug("Hotkey global: Zoom In")
            self.zoom_in.emit()
            return

        # 2. Zoom Out (Ctrl + '-')
        if char == "-" or vk in (189, 109):
            logger.debug("Hotkey global: Zoom Out")
            self.zoom_out.emit()
            return

        # 3. Zoom Reset (Ctrl + '0')
        if char == "0" or vk in (48, 96):
            logger.debug("Hotkey global: Zoom Reset")
            self.zoom_reset.emit()
            return

        # 4. Desplazamiento / Paneo con flechas (Ctrl + Flecha)
        if key == keyboard.Key.up:
            self.pan_up.emit()
        elif key == keyboard.Key.down:
            self.pan_down.emit()
        elif key == keyboard.Key.left:
            self.pan_left.emit()
        elif key == keyboard.Key.right:
            self.pan_right.emit()

    def _on_release(self, key: Any) -> None:
        """Manejador de liberación de teclas."""
        self._pressed_keys.discard(key)
