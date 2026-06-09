# 启动 MIMOClaw（开发模式）

# 确保 Node.js 在 PATH 中（从注册表获取系统 PATH）
$sysPath = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$env:PATH = "$sysPath;$env:PATH"

# 1. 启动后端
$backendDir = Join-Path $PSScriptRoot "backend"
$backendPort = 2026

Write-Host "正在启动后端..." -ForegroundColor Green
$backendJob = Start-Job -ScriptBlock {
    param($dir, $port)
    Set-Location $dir
    $env:BACKEND_PORT = $port
    python main.py
} -ArgumentList $backendDir, $backendPort

Start-Sleep -Seconds 3

# 2. 启动前端 (Vite dev server)
$frontendDir = Join-Path $PSScriptRoot "frontend"
Write-Host "正在启动前端..." -ForegroundColor Green
Set-Location $frontendDir
npm run dev
