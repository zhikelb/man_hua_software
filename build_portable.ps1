$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
$pyinstaller = Join-Path $root ".venv\Scripts\pyinstaller.exe"
$distRoot = Join-Path $root "dist"
$buildRoot = Join-Path $root "build"
$portableTarget = Join-Path $root "dist_portable"

if (-not (Test-Path $python)) {
    throw "Virtual environment python not found: $python"
}

if (-not (Test-Path $pyinstaller)) {
    & $python -m pip install pyinstaller
}

if (-not (Test-Path (Join-Path $root "requirements.txt"))) {
    throw "requirements.txt not found"
}

Write-Host "Installing/checking dependencies..." -ForegroundColor Cyan
& $python -m pip install -r (Join-Path $root "requirements.txt")

if (Test-Path $distRoot) { Remove-Item $distRoot -Recurse -Force }
if (Test-Path $buildRoot) { Remove-Item $buildRoot -Recurse -Force }

Write-Host "Building portable package with PyInstaller..." -ForegroundColor Cyan
& $pyinstaller "build_exe.spec" --distpath $distRoot --workpath $buildRoot --clean

$portableSourceDir = Get-ChildItem -Path $distRoot -Directory | Select-Object -First 1
if ($null -eq $portableSourceDir) {
    throw "Build failed: no output directory found in dist"
}

$portableSource = $portableSourceDir.FullName
$mainExe = Get-ChildItem -Path $portableSource -Filter "*.exe" -File | Select-Object -First 1
if ($null -eq $mainExe) {
    throw "Build failed: no exe found in $portableSource"
}

if (Test-Path $portableTarget) {
    Remove-Item $portableTarget -Recurse -Force
}
New-Item -ItemType Directory -Path $portableTarget | Out-Null

Write-Host "Syncing dist_portable..." -ForegroundColor Cyan
Copy-Item (Join-Path $portableSource "*") $portableTarget -Recurse -Force

if (Test-Path (Join-Path $root "data")) {
    Copy-Item (Join-Path $root "data") (Join-Path $portableTarget "data") -Recurse -Force
}

$portableReadme = Join-Path $portableTarget "README.md"
$portableLauncher = Join-Path $portableTarget "start_app.bat"

$portableReadmeContent = @(
    '# Manga Reader Portable'
    ''
    '## Start'
    '- Double-click start_app.bat'
    '- Or double-click the exe in this folder'
    ''
    '## Folders'
    '- data/: app data (database, config, covers, imports)'
    '- _internal/: runtime dependencies (do not delete)'
    ''
    '## Notes'
    '- This build uses copy import mode.'
    '- Keep and back up data/ when upgrading.'
) -join "`r`n"
Set-Content -Path $portableReadme -Value $portableReadmeContent -Encoding UTF8

$launcherContent = @(
    '@echo off'
    'chcp 65001 >nul'
    'cd /d %~dp0'
    'for %%F in (*.exe) do ('
    '  start "" "%%F"'
    '  goto :eof'
    ')'
    'echo No executable found in current folder.'
) -join "`r`n"
Set-Content -Path $portableLauncher -Value $launcherContent -Encoding UTF8

Write-Host ("Portable build completed: " + $portableTarget) -ForegroundColor Green
