$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
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
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed with exit code $LASTEXITCODE"
}

if (Test-Path $distRoot) { Remove-Item $distRoot -Recurse -Force }
if (Test-Path $buildRoot) { Remove-Item $buildRoot -Recurse -Force }

Write-Host "Building portable package with PyInstaller..." -ForegroundColor Cyan
& $pyinstaller "packaging\build_exe.spec" --distpath $distRoot --workpath $buildRoot --clean
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

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
$portableLauncherCn = Join-Path $portableTarget "启动应用.bat"

$portableReadmeContent = @(
    '# 漫画阅读器便携版'
    ''
    '## 启动方式'
    '- 双击 start_app.bat'
    '- 或双击 启动应用.bat'
    '- 也可以直接运行本目录下的 exe'
    ''
    '## 目录说明'
    '- data/: 应用数据（数据库、配置、封面缓存、导入原图）'
    '- _internal/: 运行时依赖，不要手动删除'
    ''
    '## 说明'
    '- 默认使用 copy 导入模式。'
    '- 升级程序时请保留并备份 data/。'
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
Set-Content -Path $portableLauncherCn -Value $launcherContent -Encoding UTF8

Write-Host ("Portable build completed: " + $portableTarget) -ForegroundColor Green
