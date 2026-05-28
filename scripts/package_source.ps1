param(
    [string]$Version = "local",
    [string]$OutputDir = "release"
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$distDir = Join-Path $projectRoot $OutputDir
$packageName = "bom-system-source-$Version"
$packageDir = Join-Path $distDir $packageName
$zipPath = Join-Path $distDir "$packageName.zip"
$stagingDir = Join-Path ([System.IO.Path]::GetTempPath()) "$packageName-$(New-Guid)"

Write-Host "Cleaning old source package..."
Remove-Item -LiteralPath $packageDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

$excludeDirs = @(
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".venv",
    ".build-venv",
    "node_modules",
    "build",
    "dist",
    "release",
    "offline",
    (Join-Path $projectRoot "backend\.venv"),
    (Join-Path $projectRoot "backend\.build-venv"),
    (Join-Path $projectRoot "backend\build"),
    (Join-Path $projectRoot "backend\dist"),
    (Join-Path $projectRoot "frontend\node_modules"),
    (Join-Path $projectRoot "frontend\dist"),
    (Join-Path $projectRoot "release"),
    (Join-Path $projectRoot "offline")
)

$excludeFiles = @(
    ".env",
    "*.pyc",
    "*.pyo",
    "*.spec"
)

Write-Host "Copying source code..."
robocopy $projectRoot $stagingDir /E /XD $excludeDirs /XF $excludeFiles | Out-Null
$exitCode = $LASTEXITCODE
if ($exitCode -ge 8) {
    throw "robocopy failed with exit code $exitCode"
}

Write-Host "Creating source zip archive..."
Compress-Archive -Path (Join-Path $stagingDir "*") -DestinationPath $zipPath -Force
if (!(Test-Path -LiteralPath $zipPath)) {
    throw "Source package zip was not created: $zipPath"
}
Copy-Item -LiteralPath $stagingDir -Destination $packageDir -Recurse -Force
Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Source package completed: $zipPath"
exit 0
