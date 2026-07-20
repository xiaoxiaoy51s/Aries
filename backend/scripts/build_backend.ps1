# 构建后端 exe 并 staging 到 frontend/resources/
# 用法: cd backend && .\scripts\build_backend.ps1

$ErrorActionPreference = "Stop"
$BackendRoot = Split-Path -Parent $PSScriptRoot
$FrontendResources = Join-Path $BackendRoot "..\frontend\resources" | Resolve-Path -ErrorAction SilentlyContinue
if (-not $FrontendResources) {
    $FrontendResources = (Join-Path $BackendRoot "..\frontend\resources")
    New-Item -ItemType Directory -Force -Path $FrontendResources | Out-Null
    $FrontendResources = (Resolve-Path $FrontendResources).Path
}

Write-Host "==> [1/4] Build backend/cli (TypeScript + production node_modules)"
Push-Location (Join-Path $BackendRoot "cli")
if (-not (Test-Path "node_modules")) {
    npm ci
    if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
} else {
    Write-Host "    node_modules exists, skip npm ci"
}
node node_modules/typescript/bin/tsc
if ($LASTEXITCODE -ne 0) {
    Write-Host "    tsc build failed"
    Pop-Location; exit $LASTEXITCODE
}
npm prune --omit=dev 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "npm prune skipped (node-pty may be locked by running backend). Copying full node_modules."
}
Pop-Location

Write-Host "==> [2/4] Check backend/bin/rg.exe"
$RgSrc = Join-Path $BackendRoot "bin\rg.exe"
if (-not (Test-Path $RgSrc)) {
    Write-Warning "缺少 backend/bin/rg.exe，文件搜索将回退到 Python 实现。"
}

Write-Host "==> [3/4] PyInstaller -> dist/aries.exe"
Push-Location $BackendRoot
python -m pip install --upgrade pip pyinstaller | Out-Null
python -m pip install -r requirements.txt | Out-Null
pyinstaller aries.spec --noconfirm
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
Pop-Location

Write-Host "==> [4/4] Stage frontend/resources (exe + bin + cli)"
Copy-Item (Join-Path $BackendRoot "dist\aries.exe") (Join-Path $FrontendResources "aries_backend.exe") -Force

# bin/
$BinDest = Join-Path $FrontendResources "bin"
New-Item -ItemType Directory -Force -Path $BinDest | Out-Null
if (Test-Path $RgSrc) {
    Copy-Item $RgSrc (Join-Path $BinDest "rg.exe") -Force
}

# cli/ - dist + node_modules + package.json（node-pty 原生模块需随包分发）
$CliSrc = Join-Path $BackendRoot "cli"
$CliDest = Join-Path $FrontendResources "cli"
if (Test-Path $CliDest) { Remove-Item $CliDest -Recurse -Force }
New-Item -ItemType Directory -Force -Path $CliDest | Out-Null
Copy-Item (Join-Path $CliSrc "dist") (Join-Path $CliDest "dist") -Recurse
Copy-Item (Join-Path $CliSrc "package.json") $CliDest
if (Test-Path (Join-Path $CliSrc "package-lock.json")) {
    Copy-Item (Join-Path $CliSrc "package-lock.json") $CliDest
}
Copy-Item (Join-Path $CliSrc "node_modules") (Join-Path $CliDest "node_modules") -Recurse

Write-Host ""
Write-Host "Done."
Write-Host "  Backend exe : $FrontendResources\aries_backend.exe"
Write-Host "  Ripgrep     : $FrontendResources\bin\rg.exe"
Write-Host "  CLI server  : $FrontendResources\cli"
Write-Host ""
Write-Host "Next: cd frontend && npm run electron:build"
