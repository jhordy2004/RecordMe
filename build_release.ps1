# Script automatizado de compilación y empaquetado para Windows
# Genera:
# 1. Ejecutable OneFile portable: Release/RecordMe.exe
# 2. Paquete comprimido OneDir: Release/RecordMe-v<Version>-windows-x64.zip
# 3. Instalador profesional Inno Setup: Release/RecordMe_Setup_v<Version>.exe
# Y replica en la carpeta Relase según solicitado.

param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot

# Resolver versión automáticamente si no se suministra
if (-not $Version) {
    if ($env:GITHUB_REF_NAME -and $env:GITHUB_REF_NAME.StartsWith("v")) {
        $Version = $env:GITHUB_REF_NAME.Substring(1)
    } elseif ($env:APP_VERSION) {
        $Version = $env:APP_VERSION
    } else {
        $initPy = Join-Path $ProjectRoot "src\recordme\__init__.py"
        if (Test-Path $initPy) {
            $match = Select-String -Path $initPy -Pattern '__version__\s*=\s*["'']([^"'']+)["'']'
            if ($match) {
                $Version = $match.Matches[0].Groups[1].Value
            }
        }
    }
}
if (-not $Version) {
    $Version = "0.1.1"
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  RecordMe - Compilación y Empaquetado Release v$Version   " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$ReleaseDir = Join-Path $ProjectRoot "Release"
$RelaseDir = Join-Path $ProjectRoot "Relase"

# 1. Crear directorios Release y Relase
if (-not (Test-Path $ReleaseDir)) { New-Item -ItemType Directory -Path $ReleaseDir | Out-Null }
if (-not (Test-Path $RelaseDir)) { New-Item -ItemType Directory -Path $RelaseDir | Out-Null }

# 2. Compilar con PyInstaller
Write-Host "`n[1/4] Ejecutando PyInstaller (OneFile y OneDir)..." -ForegroundColor Yellow
$PyInstaller = Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $PyInstaller)) {
    $PyInstaller = "pyinstaller"
}

& $PyInstaller --noconfirm --clean (Join-Path $ProjectRoot "recordme.spec")
if ($LASTEXITCODE -ne 0) {
    Write-Error "Fallo durante la ejecución de PyInstaller."
}

# 3. Copiar ejecutable OneFile a Release
$OneFileExe = Join-Path $ProjectRoot "dist\RecordMe.exe"
if (Test-Path $OneFileExe) {
    Write-Host "`n[2/4] Copiando ejecutable OneFile a Release/RecordMe.exe..." -ForegroundColor Green
    Copy-Item -Path $OneFileExe -Destination (Join-Path $ReleaseDir "RecordMe.exe") -Force
    Copy-Item -Path $OneFileExe -Destination (Join-Path $RelaseDir "RecordMe.exe") -Force
} else {
    Write-Warning "No se encontró dist/RecordMe.exe."
}

# 4. Crear ZIP de la versión OneDir
$OneDirFolder = Join-Path $ProjectRoot "dist\RecordMe_dir"
$ZipTarget = Join-Path $ReleaseDir "RecordMe-v${Version}-windows-x64.zip"
if (Test-Path $OneDirFolder) {
    Write-Host "`n[3/4] Creando archivo ZIP portable de la distribución OneDir ($ZipTarget)..." -ForegroundColor Green
    if (Test-Path $ZipTarget) { Remove-Item $ZipTarget -Force }
    Compress-Archive -Path "$OneDirFolder\*" -DestinationPath $ZipTarget -CompressionLevel Optimal
    Copy-Item -Path $ZipTarget -Destination (Join-Path $RelaseDir "RecordMe-v${Version}-windows-x64.zip") -Force
}

# 5. Compilar instalador con Inno Setup
Write-Host "`n[4/4] Compilando instalador Inno Setup..." -ForegroundColor Yellow
$ISCC_Paths = @(
    "C:\Users\User\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)

$ISCC = $null
foreach ($p in $ISCC_Paths) {
    if (Test-Path $p) {
        $ISCC = $p
        break
    }
}

if ($ISCC) {
    Write-Host "Compilador Inno Setup detectado: $ISCC" -ForegroundColor Cyan
    & $ISCC "/DMyAppVersion=$Version" "/DOutputBaseFilename=RecordMe_Setup_v$Version" (Join-Path $ProjectRoot "installer.iss")
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Instalador compilado exitosamente." -ForegroundColor Green
        $Installer = Join-Path $ReleaseDir "RecordMe_Setup_v${Version}.exe"
        if (Test-Path $Installer) {
            Copy-Item -Path $Installer -Destination (Join-Path $RelaseDir "RecordMe_Setup_v${Version}.exe") -Force
        }
    } else {
        Write-Warning "Fallo la compilación de Inno Setup."
    }
} else {
    Write-Warning "ISCC.exe no fue encontrado. El instalador no pudo compilarse automáticamente."
}

# 6. Generar Checksums SHA256
Write-Host "`n=== Resumen de Archivos Generados en Release ===" -ForegroundColor Cyan
Get-ChildItem -Path $ReleaseDir | ForEach-Object {
    $hash = (Get-FileHash -Path $_.FullName -Algorithm SHA256).Hash
    $sizeMB = [math]::Round($_.Length / 1MB, 2)
    Write-Host ("  - {0,-35} ({1,6} MB) SHA256: {2}" -f $_.Name, $sizeMB, $hash) -ForegroundColor White
}

Write-Host "`n¡Proceso de Release completado exitosamente!" -ForegroundColor Green
