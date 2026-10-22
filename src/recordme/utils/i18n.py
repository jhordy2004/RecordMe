"""Sistema de internacionalización (I18n) con detección automática del sistema operativo."""

import ctypes
import logging
from typing import Any

from PySide6.QtCore import QLocale

logger = logging.getLogger(__name__)

# Diccionario central de traducciones
TRANSLATIONS: dict[str, dict[str, str]] = {
    # Barra de herramientas (Toolbar)
    "tb_record": {
        "es": "Grabar",
        "en": "Record",
        "zh": "录制",
    },
    "tb_stop": {
        "es": "Detener",
        "en": "Stop",
        "zh": "停止",
    },
    "tb_pause": {
        "es": "Pausar",
        "en": "Pause",
        "zh": "暂停",
    },
    "tb_resume": {
        "es": "Reanudar",
        "en": "Resume",
        "zh": "继续",
    },
    "tb_camera": {
        "es": "Cámara",
        "en": "Camera",
        "zh": "摄像头",
    },
    "tb_microphone": {
        "es": "Micrófono",
        "en": "Microphone",
        "zh": "麦克风",
    },
    "tb_fullscreen": {
        "es": "Pantalla Completa",
        "en": "Full Screen",
        "zh": "全屏",
    },
    "tb_area": {
        "es": "Área",
        "en": "Area",
        "zh": "区域",
    },
    "tb_teleprompter": {
        "es": "Teleprompter",
        "en": "Teleprompter",
        "zh": "提词器",
    },
    "tb_censor": {
        "es": "+ Censurar",
        "en": "+ Censor",
        "zh": "+ 打码",
    },
    "tb_exit": {
        "es": "✕ Salir",
        "en": "✕ Exit",
        "zh": "✕ 退出",
    },
    "tb_zoom": {
        "es": "Zoom",
        "en": "Zoom",
        "zh": "缩放",
    },
    "tb_saving": {
        "es": "Guardando...",
        "en": "Saving...",
        "zh": "保存中...",
    },
    "tb_shortcut": {
        "es": "Atajo",
        "en": "Shortcut",
        "zh": "快捷键",
    },

    # Diálogo de Cámara
    "cam_dialog_title": {
        "es": "Cámara",
        "en": "Camera",
        "zh": "摄像头",
    },
    "cam_title": {
        "es": "Cámara",
        "en": "Camera",
        "zh": "摄像头",
    },
    "cam_header": {
        "es": "Ajustes de Cámara",
        "en": "Camera Settings",
        "zh": "摄像头设置",
    },
    "cam_shape": {
        "es": "Forma de cámara:",
        "en": "Camera shape:",
        "zh": "摄像头形状:",
    },
    "cam_shape_rect": {
        "es": "Rectángulo (sin bordes)",
        "en": "Rectangle (borderless)",
        "zh": "矩形（无边框）",
    },
    "cam_shape_circle": {
        "es": "Círculo (sin bordes)",
        "en": "Circle (borderless)",
        "zh": "圆形（无边框）",
    },
    "cam_size": {
        "es": "Tamaño:",
        "en": "Size:",
        "zh": "尺寸:",
    },
    "cam_width": {
        "es": "Ancho:",
        "en": "Width:",
        "zh": "宽度:",
    },
    "cam_height": {
        "es": "Alto:",
        "en": "Height:",
        "zh": "高度:",
    },
    "cam_name_label": {
        "es": "Nombre / Etiqueta:",
        "en": "Name / Label:",
        "zh": "姓名 / 标签:",
    },
    "cam_name_placeholder": {
        "es": "Opcional (Ej. Tu nombre)",
        "en": "Optional (e.g. Your name)",
        "zh": "可选（例如 您的姓名）",
    },
    "cam_virtual_bg": {
        "es": "Fondo Virtual (Zoom-style):",
        "en": "Virtual Background (Zoom-style):",
        "zh": "虚拟背景（类似Zoom）:",
    },
    "cam_browse_bg": {
        "es": "Seleccionar Imagen de Fondo...",
        "en": "Select Background Image...",
        "zh": "选择背景图片...",
    },
    "cam_remove_bg": {
        "es": "✕ Quitar fondo",
        "en": "✕ Remove background",
        "zh": "✕ 移除背景",
    },
    "cam_live_preview": {
        "es": "Vista previa en tiempo real",
        "en": "Real-time preview",
        "zh": "实时预览",
    },
    "cam_select_bg_dialog": {
        "es": "Seleccionar fondo virtual",
        "en": "Select virtual background",
        "zh": "选择虚拟背景",
    },
    "cam_image_filter": {
        "es": "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)",
        "en": "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        "zh": "图片 (*.png *.jpg *.jpeg *.bmp *.webp)",
    },

    # Editor de Teleprompter
    "tp_title": {
        "es": "Teleprompter",
        "en": "Teleprompter",
        "zh": "提词器",
    },
    "tp_header": {
        "es": "Teleprompter",
        "en": "Teleprompter",
        "zh": "提词器",
    },
    "tp_open_txt": {
        "es": "Abrir archivo...",
        "en": "Open file...",
        "zh": "打开文件...",
    },
    "tp_open_file": {
        "es": "Abrir archivo...",
        "en": "Open file...",
        "zh": "打开文件...",
    },
    "tp_save_script": {
        "es": "Guardar guion...",
        "en": "Save script...",
        "zh": "保存脚本...",
    },
    "tp_placeholder": {
        "es": "Pega o escribe aquí el texto de tu guion...",
        "en": "Paste or type your script here...",
        "zh": "在此粘贴或输入脚本...",
    },
    "tp_speed": {
        "es": "Velocidad de lectura:",
        "en": "Reading speed:",
        "zh": "语速:",
    },
    "tp_sec_per_line": {
        "es": "seg / línea",
        "en": "sec / line",
        "zh": "秒 / 行",
    },
    "tp_font_size": {
        "es": "Tamaño de letra:",
        "en": "Font size:",
        "zh": "字体大小:",
    },
    "tp_lines_visible": {
        "es": "Líneas visibles en pantalla:",
        "en": "Visible lines on screen:",
        "zh": "屏幕可见行数:",
    },
    "tp_lines_suffix": {
        "es": "líneas",
        "en": "lines",
        "zh": "行",
    },
    "tp_opacity": {
        "es": "Opacidad del fondo:",
        "en": "Background opacity:",
        "zh": "背景不透明度:",
    },
    "tp_test": {
        "es": "▶ Probar Teleprompter",
        "en": "▶ Test Teleprompter",
        "zh": "▶ 测试提词器",
    },
    "tp_stop_test": {
        "es": "⏹ Detener prueba",
        "en": "⏹ Stop test",
        "zh": "⏹ 停止测试",
    },
    "tp_apply": {
        "es": "Aplicar y Mostrar",
        "en": "Apply & Show",
        "zh": "应用并显示",
    },
    "tp_stats": {
        "es": "{words} palabras — Duración total estimada: {seconds} s ({mins:02d}:{secs:02d})",
        "en": "{words} words — Estimated duration: {seconds} s ({mins:02d}:{secs:02d})",
        "zh": "{words} 词 — 预计时长: {seconds} 秒 ({mins:02d}:{secs:02d})",
    },

    # Teleprompter flotante
    "tp_float_start": {
        "es": "▶ Iniciar",
        "en": "▶ Start",
        "zh": "▶ 开始",
    },
    "tp_float_pause": {
        "es": "⏸ Pausar",
        "en": "⏸ Pause",
        "zh": "⏸ 暂停",
    },
    "tp_float_resume": {
        "es": "▶ Reanudar",
        "en": "▶ Resume",
        "zh": "▶ 继续",
    },
    "tp_float_restart": {
        "es": "⏮ Reiniciar",
        "en": "⏮ Restart",
        "zh": "⏮ 重置",
    },

    # Cajas de censura y selector
    "tb_censor_tooltip": {
        "es": "Añadir recuadro flotante de censura ajustable",
        "en": "Add adjustable floating censor box",
        "zh": "添加可调节的浮动打码框",
    },
    "censor_duplicate": {
        "es": "📋 Duplicar",
        "en": "📋 Duplicate",
        "zh": "📋 复制",
    },
    "censor_guide": {
        "es": "Arrastra para seleccionar el área a censurar. Presiona ESC para cancelar.",
        "en": "Drag to select area to censor. Press ESC to cancel.",
        "zh": "拖动以选择要打码的区域。按 ESC 取消。",
    },
    "censor_selector_guide": {
        "es": "Haz clic y arrastra para definir el área que deseas censurar\n(Presiona Escape para cancelar)",
        "en": "Click and drag to define the area you want to censor\n(Press Escape to cancel)",
        "zh": "点击并拖动以定义需要打码的区域\n(按 Escape 取消)",
    },
    "censor_selector_dimensions": {
        "es": "Censura: {w}×{h} px",
        "en": "Censor: {w}×{h} px",
        "zh": "打码: {w}×{h} 像素",
    },
    "censor_mode_blur": {
        "es": "Desenfoque",
        "en": "Blur",
        "zh": "模糊",
    },
    "censor_mode_pixelate": {
        "es": "Pixelado",
        "en": "Pixelate",
        "zh": "马赛克",
    },
    "censor_mode_solid": {
        "es": "Sólido",
        "en": "Solid",
        "zh": "纯色",
    },
    "censor_drag_to_move": {
        "es": "(Arrastra para mover)",
        "en": "(Drag to move)",
        "zh": "(拖动以移动)",
    },

    # Marco de área y selector de región
    "area_header": {
        "es": "Área: {w}×{h}",
        "en": "Area: {w}×{h}",
        "zh": "区域: {w}×{h}",
    },
    "region_selector_guide": {
        "es": "Haz clic y arrastra para seleccionar el área a grabar.\n(Enter: pantalla completa | Esc: cancelar)",
        "en": "Click and drag to select recording area.\n(Enter: full screen | Esc: cancel)",
        "zh": "点击并拖动以选择录制区域。\n(Enter: 全屏 | Esc: 取消)",
    },
    "region_selector_dimensions": {
        "es": "{w} × {h} px (Enter: confirmar, Esc: cancelar)",
        "en": "{w} × {h} px (Enter: confirm, Esc: cancel)",
        "zh": "{w} × {h} 像素 (Enter: 确认, Esc: 取消)",
    },
    "btn_delete_region": {
        "es": "Eliminar selección de área (Esc)",
        "en": "Remove area selection (Esc)",
        "zh": "删除区域选择 (Esc)",
    },

    # HUD de Zoom
    "zoom_hud": {
        "es": "Zoom {pct}% | Flechas o <>: Mover",
        "en": "Zoom {pct}% | Arrows or <>: Pan",
        "zh": "缩放 {pct}% | 方向键或 <>: 移动",
    },
    "zoom_badge_tooltip": {
        "es": "Zoom activo (Usa Ctrl++ para aumentar, Ctrl+- para reducir, Ctrl+Flechas para moverte)",
        "en": "Active zoom (Use Ctrl++ to zoom in, Ctrl+- to zoom out, Ctrl+Arrows to pan)",
        "zh": "当前缩放 (使用 Ctrl++ 放大, Ctrl+- 缩小, Ctrl+方向键平移)",
    },
    "tb_exit_tooltip": {
        "es": "Cerrar RecordMe",
        "en": "Exit RecordMe",
        "zh": "退出 RecordMe",
    },

    # Comunes
    "btn_accept": {
        "es": "Aceptar",
        "en": "Accept",
        "zh": "确定",
    },
    "btn_cancel": {
        "es": "Cancelar",
        "en": "Cancel",
        "zh": "取消",
    },
    "btn_close": {
        "es": "Cerrar",
        "en": "Close",
        "zh": "关闭",
    },
    "btn_open_folder": {
        "es": "Abrir Carpeta",
        "en": "Open Folder",
        "zh": "打开文件夹",
    },

    # Diálogos de guardado y fin
    "save_dialog_title": {
        "es": "Guardar video de grabación",
        "en": "Save recorded video",
        "zh": "保存录制视频",
    },
    "save_dialog_filter": {
        "es": "Video MP4 (*.mp4)",
        "en": "MP4 Video (*.mp4)",
        "zh": "MP4 视频 (*.mp4)",
    },
    "recording_finished_title": {
        "es": "Grabación Finalizada",
        "en": "Recording Finished",
        "zh": "录制已完成",
    },
    "recording_finished_msg": {
        "es": "El video se ha guardado exitosamente en:\n{path}",
        "en": "The video was successfully saved to:\n{path}",
        "zh": "视频已成功保存至:\n{path}",
    },
    "recording_error_title": {
        "es": "Error de Grabación",
        "en": "Recording Error",
        "zh": "录制错误",
    },
    "recording_error_msg": {
        "es": "Ocurrió un error durante la grabación:\n{err}",
        "en": "An error occurred during recording:\n{err}",
        "zh": "录制过程中发生错误:\n{err}",
    },
}

_current_language: str = "en"


def detect_system_language() -> str:
    """Detecta el idioma del sistema operativo.

    Soporta Español ('es'), Chino ('zh') e Inglés ('en').
    - Si el sistema tiene Español -> 'es'.
    - Si el sistema tiene Chino -> 'zh'.
    - Si el sistema tiene Inglés -> 'en'.
    - Para cualquier otro idioma del sistema operativo, por defecto retorna Inglés ('en').
    """
    # 1. En Windows: Consulta GetUserDefaultUILanguage y GetUserDefaultLocaleName
    try:
        kernel32 = getattr(ctypes, "windll", None)
        if kernel32 and hasattr(kernel32, "kernel32"):
            lang_id = kernel32.kernel32.GetUserDefaultUILanguage()
            primary = lang_id & 0x3FF
            if primary == 0x0A:  # LANG_SPANISH
                return "es"
            elif primary == 0x04:  # LANG_CHINESE
                return "zh"
            elif primary == 0x09:  # LANG_ENGLISH
                return "en"

            buf = ctypes.create_unicode_buffer(85)
            if kernel32.kernel32.GetUserDefaultLocaleName(buf, 85) > 0:
                loc = buf.value.lower()
                if loc.startswith("es"):
                    return "es"
                elif loc.startswith("zh"):
                    return "zh"
                elif loc.startswith("en"):
                    return "en"
    except Exception as e:
        logger.debug("Error obteniendo idioma con Windows API: %s", e)

    # 2. Detección mediante QLocale de Qt (uiLanguages y system name)
    try:
        ui_langs = QLocale.system().uiLanguages()
        for lang in ui_langs:
            lang_lower = lang.lower()
            if lang_lower.startswith("es"):
                return "es"
            elif lang_lower.startswith("zh"):
                return "zh"
            elif lang_lower.startswith("en"):
                return "en"

        q_lang = QLocale.system().name().lower()
        if q_lang.startswith("es"):
            return "es"
        elif q_lang.startswith("zh"):
            return "zh"
        elif q_lang.startswith("en"):
            return "en"
    except Exception as e:
        logger.debug("Error con QLocale: %s", e)

    # 3. Fallback universal por defecto si es cualquier otro idioma: Inglés ('en')
    return "en"


def init_language(forced_lang: str | None = None) -> str:
    """Inicializa el idioma global de la aplicación."""
    global _current_language
    if forced_lang in ("es", "en", "zh"):
        _current_language = forced_lang
    else:
        _current_language = detect_system_language()
    logger.info("Idioma de la aplicación configurado en: %s", _current_language)
    return _current_language


def get_current_language() -> str:
    """Retorna el código de idioma actual."""
    return _current_language


def tr(key: str, **kwargs: Any) -> str:
    """Traduce la clave al idioma actual con soporte para interpolación de variables."""
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key

    text = entry.get(_current_language) or entry.get("en") or entry.get("es") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
