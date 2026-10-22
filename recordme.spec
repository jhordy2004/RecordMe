# -*- mode: python ; coding: utf-8 -*-
"""Especificación de PyInstaller para RecordMe."""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

project_root = Path(SPECPATH).resolve()
src_dir = project_root / "src"
site_packages = Path(sys.prefix) / "Lib" / "site-packages"

# Recolectar dependencias completas
datas = [
    (str(project_root / "src" / "recordme" / "resources" / "selfie_segmentation.onnx"), "recordme/resources"),
    (str(project_root / "src" / "recordme" / "resources" / "ico"), "recordme/resources/ico"),
    (str(project_root / "src" / "recordme" / "resources" / "ico"), "resources/ico"),
    (str(project_root / "src" / "recordme" / "resources" / "ico"), "ico"),
]

binaries = []

# Binario de FFmpeg de imageio_ffmpeg
imageio_bin_dir = site_packages / "imageio_ffmpeg" / "binaries"
if imageio_bin_dir.exists():
    for f in imageio_bin_dir.glob("ffmpeg*"):
        datas.append((str(f), "imageio_ffmpeg/binaries"))
        datas.append((str(f), "binaries"))
        binaries.append((str(f), "imageio_ffmpeg/binaries"))
        binaries.append((str(f), "."))

# Recolectar módulos y metadatos de paquetes críticos
for pkg in ("pynput", "sounddevice", "soundfile", "platformdirs", "imageio_ffmpeg", "dxcam", "docx"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas.extend(pkg_datas)
        binaries.extend(pkg_binaries)
    except Exception:
        pass

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "numpy",
    "cv2",
    "mss",
    "sounddevice",
    "soundfile",
    "pynput",
    "pynput.keyboard",
    "pynput.mouse",
    "platformdirs",
    "imageio_ffmpeg",
    "docx",
    "comtypes",
    "comtypes.client",
    "recordme",
    "recordme.app",
    "recordme.platform_services.windows",
    "recordme.capture.windows_dxcam",
    "recordme.capture.mss_fallback",
    "recordme.capture.qt_fallback",
]

a = Analysis(
    [str(src_dir / "recordme" / "__main__.py")],
    pathex=[str(src_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "email", "http", "xmlrpc"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Configuración OneFile
exe_onefile = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="RecordMe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "src" / "recordme" / "resources" / "ico" / "icono_256.ico"),
)

# Configuración OneDir (para empaquetado Inno Setup y zip de alto rendimiento)
exe_onedir = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RecordMe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(project_root / "src" / "recordme" / "resources" / "ico" / "icono_256.ico"),
)

coll = COLLECT(
    exe_onedir,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="RecordMe_dir",
)
