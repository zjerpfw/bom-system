param(
    [string]$Version = "local",
    [string]$OutputDir = "release",
    [switch]$ReuseBuildVenv,
    [switch]$SkipFrontendBuild,
    [string]$ExistingPython = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [string]$Description,
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        $exitCode = $LASTEXITCODE
        throw "$Description failed, exit code: $exitCode"
    }
}

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$distDir = Join-Path $projectRoot $OutputDir
$packageName = "bom-system-windows-$Version"
$packageDir = Join-Path $distDir $packageName
$serverDir = Join-Path $packageDir "server"
$dataDir = Join-Path $serverDir "data"
$modelsDir = Join-Path $serverDir "models"
$frontendDistDir = Join-Path $frontendDir "dist"
$buildVenvDir = Join-Path $backendDir ".build-venv"
$buildPython = Join-Path $buildVenvDir "Scripts\python.exe"
$cythonUtilityDir = Join-Path $buildVenvDir "Lib\site-packages\Cython\Utility"
$paddleocrPackageDir = Join-Path $buildVenvDir "Lib\site-packages\paddleocr"
$paddleLibsDir = Join-Path $buildVenvDir "Lib\site-packages\paddle\libs"

Write-Host "Cleaning old package directory..."
Remove-Item -LiteralPath $packageDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $serverDir, $dataDir, $modelsDir | Out-Null

Write-Host "Installing and building frontend..."
Push-Location $frontendDir
if ($SkipFrontendBuild) {
    if (!(Test-Path -LiteralPath (Join-Path $frontendDistDir "index.html"))) {
        throw "Frontend dist does not exist. Run pnpm build first or remove -SkipFrontendBuild."
    }
    Write-Host "Using existing frontend dist..."
} else {
    Invoke-Checked "Install frontend dependencies" { pnpm install --frozen-lockfile }
    Invoke-Checked "Build frontend" { pnpm build }
}
Pop-Location

Write-Host "Installing backend dependencies..."
Push-Location $backendDir
if ($ExistingPython -ne "") {
    $buildPython = $ExistingPython
    if (!(Test-Path -LiteralPath $buildPython)) {
        throw "Existing Python does not exist: $buildPython"
    }
    & $buildPython -c "import PyInstaller" *> $null
    if ($LASTEXITCODE -ne 0) {
        & $buildPython -m pip --version *> $null
        if ($LASTEXITCODE -ne 0) {
            Invoke-Checked "Enable pip" { & $buildPython -m ensurepip --upgrade }
        }
        Invoke-Checked "Install PyInstaller into existing Python" { & $buildPython -m pip install pyinstaller }
    }
    Write-Host "Using existing Python for PyInstaller: $buildPython"
} elseif ($ReuseBuildVenv -and (Test-Path -LiteralPath $buildPython)) {
    Write-Host "Reusing backend build venv..."
} else {
    Remove-Item -LiteralPath $buildVenvDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Invoke-Checked "Create backend build venv" { uv venv $buildVenvDir --python 3.11 }
    } else {
        Invoke-Checked "Create backend build venv" { python -m venv $buildVenvDir }
    }
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Invoke-Checked "Install backend dependencies with uv" { uv pip install --python $buildPython -r requirements.txt }
    } else {
        & $buildPython -m pip --version *> $null
        if ($LASTEXITCODE -ne 0) {
            Invoke-Checked "Enable pip" { & $buildPython -m ensurepip --upgrade }
        }
        Invoke-Checked "Install backend dependencies with pip" { & $buildPython -m pip install -r requirements.txt }
    }
}

Write-Host "Building backend EXE with PyInstaller..."
if (!(Test-Path -LiteralPath (Join-Path $cythonUtilityDir "CppSupport.cpp"))) {
    throw "Cython Utility data is missing: $cythonUtilityDir"
}
if (!(Test-Path -LiteralPath (Join-Path $paddleocrPackageDir "tools\__init__.py"))) {
    throw "PaddleOCR dynamic source data is missing: $paddleocrPackageDir"
}
if (!(Test-Path -LiteralPath (Join-Path $paddleLibsDir "mklml.dll"))) {
    throw "Paddle native libraries are missing: $paddleLibsDir"
}
Invoke-Checked "Build backend EXE" {
    & $buildPython -m PyInstaller `
        --noconfirm `
        --clean `
        --name bom-server `
        --console `
        --add-data "$frontendDistDir;frontend_dist" `
        --add-data "$cythonUtilityDir;Cython\Utility" `
        --add-data "$paddleocrPackageDir;paddleocr" `
        --add-binary "$paddleLibsDir\*.dll;paddle\libs" `
        --collect-submodules skimage `
        --collect-submodules scipy `
        --collect-submodules imgaug `
        --copy-metadata imageio `
        --copy-metadata imgaug `
        --hidden-import aiosqlite `
        --hidden-import faiss `
        --hidden-import imghdr `
        --hidden-import shapely `
        --hidden-import pyclipper `
        --hidden-import imgaug `
        --hidden-import lmdb `
        --hidden-import rapidfuzz `
        --hidden-import requests `
        --hidden-import tqdm `
        --exclude-module paddle.jit.sot `
        main.py
}
Pop-Location

if (!(Test-Path -LiteralPath (Join-Path $backendDir "dist\bom-server"))) {
    throw "PyInstaller output directory does not exist: backend\dist\bom-server"
}
Copy-Item -Path (Join-Path $backendDir "dist\bom-server\*") -Destination $serverDir -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination (Join-Path $serverDir ".env.example")
Copy-Item -LiteralPath (Join-Path $projectRoot "docs\PACKAGE_GUIDE.md") -Destination (Join-Path $packageDir "package-guide.md")

@'
Copy models/paddleocr from the PaddleOCR offline model package into this directory.

Final structure:

models/
└── paddleocr/
    └── whl/

Then configure server/.env:

PADDLEOCR_MODEL_DIR=./models/paddleocr/whl
PADDLEOCR_ASCII_CACHE_DIR=C:\bom-system-cache\paddleocr\whl
'@ | Set-Content -LiteralPath (Join-Path $modelsDir "README.txt") -Encoding UTF8

@'
@echo off
chcp 65001 >nul
cd /d "%~dp0server"
if not exist ".env" copy ".env.example" ".env" >nul
echo BOM system is starting...
echo.
echo Browser: http://127.0.0.1:8000
echo API docs: http://127.0.0.1:8000/docs
echo.
bom-server.exe
pause
'@ | Set-Content -LiteralPath (Join-Path $packageDir "start-bom.bat") -Encoding ASCII

@'
@echo off
chcp 65001 >nul
cd /d "%~dp0server"
if not exist ".env" copy ".env.example" ".env" >nul
set BOM_RUNTIME_DIR=%CD%
start "BOM System" "%CD%\bom-server.exe"
timeout /t 3 >nul
start http://127.0.0.1:8000
'@ | Set-Content -LiteralPath (Join-Path $packageDir "start-bom-and-open-browser.bat") -Encoding ASCII

Write-Host "Creating zip archive..."
$zipPath = Join-Path $distDir "$packageName.zip"
Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $packageDir "*") -DestinationPath $zipPath -Force
if (!(Test-Path -LiteralPath $zipPath)) {
    throw "Package zip was not created: $zipPath"
}

Write-Host "Package completed: $zipPath"
