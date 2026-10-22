#!/usr/bin/env bash
# Script de empaquetado de RecordMe para Linux (AppImage)
set -e

echo "=== Iniciando empaquetado de RecordMe para Linux (AppImage) ==="

APP_NAME="RecordMe"
VERSION="0.1.0"
APP_DIR="dist/RecordMe.AppDir"
RELEASE_DIR="Release"

mkdir -p "${RELEASE_DIR}"
mkdir -p "${APP_DIR}/usr/bin"
mkdir -p "${APP_DIR}/usr/share/applications"
mkdir -p "${APP_DIR}/usr/share/icons/hicolor/256x256/apps"

# 1. Compilar binarios de RecordMe con PyInstaller en modo onedir (sin consola de terminal)
python -m PyInstaller \
    --name "recordme-bin" \
    --onedir \
    --noconfirm \
    --clean \
    --windowed \
    --add-data "src/recordme/resources/selfie_segmentation.onnx:recordme/resources" \
    --add-data "src/recordme/resources/ico:recordme/resources/ico" \
    --collect-all "PySide6" \
    --collect-all "imageio_ffmpeg" \
    --collect-all "sounddevice" \
    --collect-all "soundfile" \
    --collect-all "pynput" \
    --paths "src" \
    "src/recordme/__main__.py"

# 2. Copiar archivos en la estructura AppDir
cp -r dist/recordme-bin/* "${APP_DIR}/usr/bin/"

# 3. Crear archivo Desktop Entry
cat <<EOF > "${APP_DIR}/recordme.desktop"
[Desktop Entry]
Name=RecordMe
Comment=Grabador de pantalla con teleprompter, cámara y zoom dinámico
Exec=recordme-bin
Icon=recordme
Terminal=false
Type=Application
Categories=AudioVideo;Recorder;
EOF

cp "${APP_DIR}/recordme.desktop" "${APP_DIR}/usr/share/applications/"

# 4. Crear AppRun launcher
cat <<'EOF' > "${APP_DIR}/AppRun"
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/bin:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/recordme-bin" "$@"
EOF
chmod +x "${APP_DIR}/AppRun"

# 5. Descargar appimagetool si no existe y compilar
if [ ! -f "appimagetool" ]; then
    echo "Descargando appimagetool..."
    wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage -O appimagetool || true
    chmod +x appimagetool || true
fi

if [ -f "appimagetool" ]; then
    ./appimagetool "${APP_DIR}" "${RELEASE_DIR}/${APP_NAME}-${VERSION}-x86_64.AppImage"
    echo "=== AppImage generado: ${RELEASE_DIR}/${APP_NAME}-${VERSION}-x86_64.AppImage ==="
else
    echo "AppDir preparado en ${APP_DIR} (ejecuta appimagetool sobre esta carpeta para crear el AppImage final)."
fi
