"""Componentes de interfaz de usuario de RecordMe."""

from recordme.ui.camera_preview import CameraPreviewWidget
from recordme.ui.region_selector import RegionSelectorOverlay
from recordme.ui.teleprompter import TeleprompterWidget
from recordme.ui.teleprompter_editor import TeleprompterEditorDialog
from recordme.ui.toolbar import FloatingToolbar

__all__ = [
    "CameraPreviewWidget",
    "FloatingToolbar",
    "RegionSelectorOverlay",
    "TeleprompterEditorDialog",
    "TeleprompterWidget",
]
