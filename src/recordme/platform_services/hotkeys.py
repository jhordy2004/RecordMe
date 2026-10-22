"""Servicio de atajos de teclado globales del sistema usando pynput con señales Qt seguras."""

import ctypes
import logging
import sys
import threading
import time
from typing import Any

from pynput import keyboard
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    from ctypes import wintypes

    class _GUITHREADINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("hwndActive", wintypes.HWND),
            ("hwndFocus", wintypes.HWND),
            ("hwndCapture", wintypes.HWND),
            ("hwndMenuOwner", wintypes.HWND),
            ("hwndMoveSize", wintypes.HWND),
            ("hwndCaret", wintypes.HWND),
            ("rcCaret", wintypes.RECT),
        ]

    class _CURSORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("hCursor", wintypes.HANDLE),
            ("ptScreenPos", wintypes.POINT),
        ]


class GlobalHotkeyService(QObject):
    """Escucha atajos de teclado globales en segundo plano y emite señales en el hilo de Qt."""

    # Zoom y Panorámica
    zoom_in = Signal()
    zoom_out = Signal()
    zoom_reset = Signal()
    pan_up = Signal()
    pan_down = Signal()
    pan_left = Signal()
    pan_right = Signal()

    # Atajos de acciones directas (L, R, P, M, C, T, X, Q) y combinaciones Alt
    trigger_area = Signal()
    trigger_record = Signal()
    trigger_pause = Signal()
    trigger_mic = Signal()
    trigger_camera = Signal()
    trigger_teleprompter = Signal()
    trigger_censor = Signal()
    trigger_exit = Signal()
    trigger_escape = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener: keyboard.Listener | None = None
        self._pressed_keys: set[Any] = set()
        self._zoom_active: bool = False
        self._text_input_active: bool = False
        self._last_trigger_time: dict[str, float] = {}
        self._thread_local = threading.local()

    def _is_text_input_active_system_wide(self) -> bool:
        """Determina si el usuario está actualmente escribiendo en un campo de texto en cualquier aplicación."""
        if self._text_input_active:
            return True

        if sys.platform != "win32":
            return False

        user32 = ctypes.windll.user32

        # 1. Inspección de ventana activa y GUIThreadInfo nativo
        try:
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                pid = wintypes.DWORD()
                tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if tid:
                    gui = _GUITHREADINFO()
                    gui.cbSize = ctypes.sizeof(_GUITHREADINFO)
                    if user32.GetGUIThreadInfo(tid, ctypes.byref(gui)):
                        # Caret activo o parpadeando
                        if gui.hwndCaret or (gui.flags & 1) or (gui.rcCaret.right > gui.rcCaret.left):
                            return True
                        # Control hijo con clase de edición de texto
                        if gui.hwndFocus:
                            buf = ctypes.create_unicode_buffer(256)
                            user32.GetClassNameW(gui.hwndFocus, buf, 256)
                            cls_name = buf.value.lower()
                            if any(
                                k in cls_name
                                for k in (
                                    "edit",
                                    "rich",
                                    "scintilla",
                                    "text",
                                    "input",
                                    "terminal",
                                    "console",
                                    "monaco",
                                    "view",
                                )
                            ):
                                return True
        except Exception:
            pass

        # 2. Comprobación del cursor I-Beam (cursor de texto en navegadores web, WhatsApp, editores)
        try:
            ci = _CURSORINFO()
            ci.cbSize = ctypes.sizeof(_CURSORINFO)
            if user32.GetCursorInfo(ctypes.byref(ci)):
                ibeam = user32.LoadCursorW(None, 32513)  # IDC_IBEAM
                if ci.hCursor and ibeam and ci.hCursor == ibeam:
                    return True
        except Exception:
            pass

        # 3. Comprobación vía UIAutomation (Chrome, Edge, WhatsApp Desktop, Electron, Office, etc.)
        try:
            if not getattr(self._thread_local, "com_initialized", False):
                try:
                    ctypes.windll.ole32.CoInitialize(None)
                    self._thread_local.com_initialized = True
                except Exception:
                    pass

            uia = getattr(self._thread_local, "uia", None)
            if uia is None:
                try:
                    import comtypes.client
                    from comtypes.gen import UIAutomationClient

                    uia = comtypes.client.CreateObject(
                        "{ff48dba4-60ef-4201-aa87-54103eef594e}",
                        interface=UIAutomationClient.IUIAutomation,
                    )
                    self._thread_local.uia = uia
                except Exception:
                    try:
                        import comtypes.client

                        uia = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}")
                        self._thread_local.uia = uia
                    except Exception:
                        self._thread_local.uia = False

            uia = getattr(self._thread_local, "uia", None)
            if uia:
                elem = uia.GetFocusedElement()
                if elem:
                    # 50004: UIA_EditControlTypeId
                    # 50030: UIA_DocumentControlTypeId (Google Docs, contenteditable, WhatsApp Web/Desktop)
                    # 50003: UIA_ComboBoxControlTypeId
                    # 50025: UIA_CustomControlTypeId (campos web modernos personalizados)
                    # 50020: UIA_TextControlTypeId
                    ct = getattr(elem, "CurrentControlType", None)
                    if ct in (50004, 50030, 50003, 50025, 50020):
                        if getattr(elem, "CurrentHasKeyboardFocus", False):
                            return True
                        try:
                            val = elem.GetCurrentPattern(10002)  # ValuePattern
                            if val and not getattr(val, "CurrentIsReadOnly", True):
                                return True
                        except Exception:
                            pass
                        if ct in (50004, 50030, 50003):
                            return True
        except Exception:
            pass

        return False

    def _should_trigger_action(self, action_name: str, min_interval: float = 0.35) -> bool:
        """Comprueba si ha transcurrido el tiempo mínimo entre activaciones de un atajo para evitar rebotes."""
        now = time.monotonic()
        last = self._last_trigger_time.get(action_name, 0.0)
        if now - last < min_interval:
            return False
        self._last_trigger_time[action_name] = now
        return True

    def set_zoom_active(self, active: bool) -> None:
        """Habilita o deshabilita la navegación directa con flechas y <> cuando el zoom está activo."""
        self._zoom_active = active

    def set_text_input_active(self, active: bool) -> None:
        """Silencia atajos de una sola tecla (L, R, etc.) mientras el usuario escribe en un campo de texto."""
        self._text_input_active = active

    def start(self) -> bool:
        """Inicia el escuchador de teclado global."""
        try:
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
                daemon=True,
            )
            self._listener.start()
            logger.info(
                "GlobalHotkeyService iniciado (Alt+L/L: Área, Alt+R/R: Grabar/Detener, Alt+P/P: Pausa, "
                "Alt+M/M: Mic, Alt+C/C: Cámara, Alt+T/T: Teleprompter, Alt+X/X: Censura, Alt+Q/Q: Salir, Ctrl++/--: Zoom)."
            )
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

    def _is_alt_pressed(self) -> bool:
        """Verifica si alguna tecla Alt (izquierda o derecha) está presionada."""
        if sys.platform == "win32":
            try:
                # 0x12 = VK_MENU (Alt)
                if ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000:
                    return True
            except Exception:
                pass
        return any(
            k in self._pressed_keys
            for k in (
                keyboard.Key.alt,
                keyboard.Key.alt_l,
                keyboard.Key.alt_r,
                keyboard.Key.alt_gr,
            )
        )

    def _is_win_pressed(self) -> bool:
        """Verifica si alguna tecla Windows (Super/Cmd) está presionada."""
        if sys.platform == "win32":
            try:
                # 0x5B = VK_LWIN, 0x5C = VK_RWIN
                if (ctypes.windll.user32.GetAsyncKeyState(0x5B) & 0x8000) or (
                    ctypes.windll.user32.GetAsyncKeyState(0x5C) & 0x8000
                ):
                    return True
            except Exception:
                pass
        return any(
            k in self._pressed_keys
            for k in (
                keyboard.Key.cmd,
                keyboard.Key.cmd_l,
                keyboard.Key.cmd_r,
            )
        )

    def _on_press(self, key: Any) -> None:
        """Manejador de pulsación de teclas."""
        self._pressed_keys.add(key)

        char = getattr(key, "char", None)
        vk = getattr(key, "vk", None)
        char_lower = char.lower() if isinstance(char, str) else None

        ctrl = self._is_ctrl_pressed()
        alt = self._is_alt_pressed()
        win = self._is_win_pressed()

        # Tecla Escape para cancelar o eliminar selección activa
        if key == keyboard.Key.esc or vk == 27:
            if not self._is_text_input_active_system_wide():
                self.trigger_escape.emit()
                return

        # Atajos de acciones directas (L, R, P, M, C, T, X, Q) o con Alt (Alt+L, Alt+R, etc.)
        if not ctrl and not win:
            if char_lower in ("l", "r", "p", "m", "c", "t", "x", "q") or vk in (76, 82, 80, 77, 67, 84, 88, 81):
                # Si es una tecla individual directa (sin Alt), silenciar si el usuario está en un campo de texto
                if not alt:
                    if self._is_text_input_active_system_wide():
                        logger.debug("Atajo directo '%s' ignorado: campo de texto activo en primer plano.", char_lower or vk)
                        return

                combo_name = f"Alt+{char_lower.upper()}" if alt and char_lower else (char_lower.upper() if char_lower else str(vk))

                if char_lower == "l" or vk == 76:
                    if self._should_trigger_action("area", min_interval=0.4):
                        logger.info("Hotkey global detectado: Seleccionar Área (%s)", combo_name)
                        self.trigger_area.emit()
                    return
                elif char_lower == "r" or vk == 82:
                    if self._should_trigger_action("record", min_interval=0.5):
                        logger.info("Hotkey global detectado: Iniciar/Detener Grabación (%s)", combo_name)
                        self.trigger_record.emit()
                    return
                elif char_lower == "p" or vk == 80:
                    if self._should_trigger_action("pause", min_interval=0.35):
                        logger.info("Hotkey global detectado: Pausar/Reanudar (%s)", combo_name)
                        self.trigger_pause.emit()
                    return
                elif char_lower == "m" or vk == 77:
                    if self._should_trigger_action("mic", min_interval=0.3):
                        logger.info("Hotkey global detectado: Micrófono (%s)", combo_name)
                        self.trigger_mic.emit()
                    return
                elif char_lower == "c" or vk == 67:
                    if self._should_trigger_action("camera", min_interval=0.4):
                        logger.info("Hotkey global detectado: Cámara (%s)", combo_name)
                        self.trigger_camera.emit()
                    return
                elif char_lower == "t" or vk == 84:
                    if self._should_trigger_action("teleprompter", min_interval=0.4):
                        logger.info("Hotkey global detectado: Teleprompter (%s)", combo_name)
                        self.trigger_teleprompter.emit()
                    return
                elif char_lower == "x" or vk == 88:
                    if self._should_trigger_action("censor", min_interval=0.4):
                        logger.info("Hotkey global detectado: Censurar Área (%s)", combo_name)
                        self.trigger_censor.emit()
                    return
                elif char_lower == "q" or vk == 81:
                    if self._should_trigger_action("exit", min_interval=0.5):
                        logger.info("Hotkey global detectado: Salir (%s)", combo_name)
                        self.trigger_exit.emit()
                    return

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
