#!/usr/bin/env bash
# Script de empaquetado de RecordMe para macOS (.app y .dmg)
set -e

APP_NAME="RecordMe"

# Resolver versión dinámicamente si se ejecuta desde tag de Git (ej. v0.1.1 -> 0.1.1)
VERSION="${1:-}"
if [ -z "${VERSION}" ]; then
    if [ -n "${GITHUB_REF_NAME}" ] && [[ "${GITHUB_REF_NAME}" == v* ]]; then
        VERSION="${GITHUB_REF_NAME#v}"
    elif [ -n "${APP_VERSION}" ]; then
        VERSION="${APP_VERSION}"
    else
        VERSION=$(python3 -c "import re; m = re.search(r'__version__\s*=\s*[\"\\\']([^\"\\\']+)[\"\\\']', open('src/recordme/__init__.py').read()); print(m.group(1) if m else '0.1.1')" 2>/dev/null || echo "0.1.1")
    fi
fi

echo "=== Iniciando empaquetado de RecordMe v${VERSION} para macOS ==="

DIST_DIR="dist"
RELEASE_DIR="Release"

mkdir -p "${RELEASE_DIR}"

# 1. Compilar aplicación con PyInstaller en modo Windowed (.app bundle)
python -m PyInstaller \
    --name "${APP_NAME}" \
    --windowed \
    --noconfirm \
    --clean \
    --icon "src/recordme/resources/ico/icono_256.ico" \
    --add-data "src/recordme/resources/selfie_segmentation.onnx:recordme/resources" \
    --add-data "src/recordme/resources/ico:recordme/resources/ico" \
    --collect-all "PySide6" \
    --collect-all "imageio_ffmpeg" \
    --collect-all "sounddevice" \
    --collect-all "soundfile" \
    --collect-all "pynput" \
    --paths "src" \
    "src/recordme/__main__.py"

# 2. Copiar Info.plist personalizado si existe
PLIST="${DIST_DIR}/${APP_NAME}.app/Contents/Info.plist"
if [ -f "scripts/Info.plist" ]; then
    echo "Copiando scripts/Info.plist a ${PLIST}..."
    cp "scripts/Info.plist" "${PLIST}"
fi

# 3. Firmar bundle ad-hoc con entitlements
if [ -f "scripts/entitlements.mac.plist" ]; then
    echo "Firmando bundle con entitlements.mac.plist..."
    codesign --force --deep --sign - --entitlements "scripts/entitlements.mac.plist" "${DIST_DIR}/${APP_NAME}.app"
else
    codesign --force --deep --sign - "${DIST_DIR}/${APP_NAME}.app"
fi

# 4. Crear imagen de disco (.dmg) montable
echo "Generando imagen de disco DMG..."
hdiutil create -volname "${APP_NAME}" -srcfolder "${DIST_DIR}/${APP_NAME}.app" -ov -format UDZO "${RELEASE_DIR}/${APP_NAME}-${VERSION}-macOS.dmg"

echo "=== Empaquetado completado exitosamente: ${RELEASE_DIR}/${APP_NAME}-${VERSION}-macOS.dmg ==="
