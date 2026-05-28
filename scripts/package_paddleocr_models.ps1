param(
    [string]$Version = "local",
    [string]$OutputDir = "release"
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$modelRoot = Join-Path $projectRoot "offline\paddleocr"
$modelWhlRoot = Join-Path $modelRoot "whl"
$distDir = Join-Path $projectRoot $OutputDir
$packageName = "bom-system-paddleocr-models-$Version"
$packageDir = Join-Path $distDir $packageName
$zipPath = Join-Path $distDir "$packageName.zip"

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

Write-Host "Preparing PaddleOCR offline models..."
Push-Location (Join-Path $projectRoot "backend")
if (Test-Path ".build-venv\Scripts\python.exe") {
    $python = ".\.build-venv\Scripts\python.exe"
} elseif (Test-Path ".venv\Scripts\python.exe") {
    $python = ".\.venv\Scripts\python.exe"
} else {
    $python = "python"
}
Invoke-Checked "Download PaddleOCR models" { & $python (Join-Path $projectRoot "scripts\download_paddleocr_models.py") }
Pop-Location

if (!(Test-Path -LiteralPath $modelWhlRoot)) {
    throw "PaddleOCR model directory does not exist: $modelWhlRoot"
}

Write-Host "Cleaning old model package..."
Remove-Item -LiteralPath $packageDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Join-Path $packageDir "models") | Out-Null

Copy-Item -LiteralPath $modelRoot -Destination (Join-Path $packageDir "models") -Recurse -Force

$readmeLines = @(
    "# PaddleOCR Offline Model Package",
    "",
    "Copy the models directory into the EXE portable package server directory.",
    "",
    "Final structure:",
    "",
    "server/",
    "|-- bom-server.exe",
    "|-- .env",
    "|-- data/",
    "|-- models/",
    "    |-- paddleocr/",
    "        |-- whl/",
    "",
    "Then configure server/.env:",
    "",
    "PADDLEOCR_MODEL_DIR=./models/paddleocr/whl",
    "PADDLEOCR_ASCII_CACHE_DIR=C:\bom-system-cache\paddleocr\whl",
    "",
    "Prepare and copy this package before visiting an offline customer site."
)
$readmeLines | Set-Content -LiteralPath (Join-Path $packageDir "README.md") -Encoding UTF8

Write-Host "Creating model zip archive..."
Compress-Archive -Path (Join-Path $packageDir "*") -DestinationPath $zipPath -Force
if (!(Test-Path -LiteralPath $zipPath)) {
    throw "PaddleOCR model package zip was not created: $zipPath"
}
Write-Host "PaddleOCR model package completed: $zipPath"
