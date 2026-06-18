# 启动 Aries（开发模式）
# 流程：先启动后端 -> 等待 /health 就绪 -> 再启动前端 (Vite + Electron)

$sysPath = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$env:PATH = "$sysPath;$env:PATH"

$env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
$env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"

$backendDir  = Join-Path $PSScriptRoot "backend"
$frontendDir = Join-Path $PSScriptRoot "frontend"
$backendPort = 30000

# 1. 启动后端（独立窗口，便于看日志）
Write-Host "[1/2] 正在启动后端 (port $backendPort)..." -ForegroundColor Green

$backendCmd = "`$env:BACKEND_PORT='$backendPort'; Set-Location '$backendDir'; python main.py"
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit","-NoProfile","-Command",$backendCmd -WindowStyle Normal | Out-Null

# 2. 等待后端 /health 就绪
Write-Host "[等待] 探测后端 http://127.0.0.1:$backendPort/health ..." -ForegroundColor Yellow

$maxWait = 60
$elapsed = 0
$ready   = $false

while ($elapsed -lt $maxWait) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$backendPort/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
            $ready = $true
            break
        }
    } catch {
        # 后端尚未就绪
    }
    Start-Sleep -Milliseconds 500
    $elapsed += 0.5
    Write-Host "." -NoNewline -ForegroundColor DarkGray
}

Write-Host ""

if (-not $ready) {
    Write-Host "[错误] 后端在 $maxWait 秒内未就绪，前端启动已取消。" -ForegroundColor Red
    Write-Host "       请检查后端窗口的报错信息。" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] 后端已就绪。" -ForegroundColor Green

# 3. 启动前端 (Vite + Electron)
Write-Host "[2/2] 正在启动前端 (Vite + Electron)..." -ForegroundColor Green
Set-Location $frontendDir
npm run electron:dev
