"""Servicio de atajos de teclado globales del sistema usando pynput con señales Qt seguras."""

import ctypes
import logging
import sys
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
        self._zoom_active: bool = False

    def set_zoom_active(self, active: bool) -> None:
        """Habilita o deshabilita la navegación directa con flechas y <> cuando el zoom está activo."""
        self._zoom_active = active

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
        if sys.platform == "win32":
            try:
                # 0x11 = VK_CONTROL (evalúa instantáneamente el estado del teclado físico)
                if ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000:
                    return True
            except Exception:
                pass
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
        char = getattr(key, "char", None)
        vk = getattr(key, "vk", None)
        ctrl = self._is_ctrl_pressed()

        # Si el zoom está activo (>100%), permitir flechas y <> sin necesidad de presionar Ctrl
        if self._zoom_active or ctrl:
            if key == keyboard.Key.up or vk == 38:
                logger.info("Hotkey global detectado: Pan Arriba")
                self.pan_up.emit()
                return
            elif key == keyboard.Key.down or vk == 40:
                logger.info("Hotkey global detectado: Pan Abajo")
                self.pan_down.emit()
                return
            elif key == keyboard.Key.left or vk in (37, 188) or char in ("<", ","):
                logger.info("Hotkey global detectado: Pan Izquierda")
                self.pan_left.emit()
                return
            elif key == keyboard.Key.right or vk in (39, 190) or char in (">", "."):
                logger.info("Hotkey global detectado: Pan Derecha")
                self.pan_right.emit()
                return

        if not ctrl:
            return

        # 1. Zoom In (Ctrl + '+' o Ctrl + '=')
        # vk: 187=VK_OEM_PLUS, 107=VK_ADD, 43=Plus, 61=Equal
        if char in ("+", "=") or vk in (187, 107, 43, 61):
            logger.info("Hotkey global detectado: Zoom In (char=%s, vk=%s)", char, vk)
            self.zoom_in.emit()
            return

        # 2. Zoom Out (Ctrl + '-')
        # vk: 189=VK_OEM_MINUS, 109=VK_SUBTRACT, 45=Minus, 95=Underscore, 191=VK_OEM_2
        if char in ("-", "_") or vk in (189, 109, 45, 95, 191):
            logger.info("Hotkey global detectado: Zoom Out (char=%s, vk=%s)", char, vk)
            self.zoom_out.emit()
            return

        # 3. Zoom Reset (Ctrl + '0')
        # vk: 48=VK_0, 96=VK_NUMPAD0
        if char in ("0", ")") or vk in (48, 96):
            logger.info("Hotkey global detectado: Zoom Reset (char=%s, vk=%s)", char, vk)
            self.zoom_reset.emit()
            return

    def _on_release(self, key: Any) -> None:
        """Manejador de liberación de teclas."""
        self._pressed_keys.discard(key)
