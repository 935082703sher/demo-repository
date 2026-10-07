# Restart the RTMC assistant and its Telegram bot on the latest main (Windows).
#
# Usage (PowerShell, from anywhere):
#     powershell -ExecutionPolicy Bypass -File scripts\restart_bot.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\restart_bot.ps1 -Docker   # API in Docker
#
# Steps: pull main -> stop the old API and bot -> build the KB index -> start the API
# -> check the KB is loaded -> start the Telegram bot. Settings (TELEGRAM_BOT_TOKEN,
# AI_RAG_ONLY, the model key, ...) are read from the repo's .env as before.

param([switch]$Docker, [int]$Port = 8000)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

Write-Host "1/5 main yangilanmoqda..." -ForegroundColor Cyan
git checkout main
git pull origin main

Write-Host "2/5 eski API va bot to'xtatilmoqda..." -ForegroundColor Cyan
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" |
    Where-Object { $_.CommandLine -match "uvicorn.*app\.main|telegram_polling\.py" } |
    ForEach-Object {
        Write-Host "   to'xtatildi: PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Write-Host "3/5 bilimlar bazasi qurilmoqda..." -ForegroundColor Cyan
& $Python kb/src/build_kb.py | Out-Null

Write-Host "4/5 API ishga tushirilmoqda..." -ForegroundColor Cyan
if ($Docker) {
    docker compose up -d --build
} else {
    Start-Process -FilePath $Python -WorkingDirectory $Root `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port"
}

$health = $null
for ($i = 0; $i -lt 60; $i++) {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/assistant/health" -TimeoutSec 2
        break
    } catch { Start-Sleep -Seconds 1 }
}
if ($null -eq $health) {
    Write-Host "API javob bermadi. API oynasidagi xatoni tekshiring." -ForegroundColor Red
    exit 1
}
if ($health.chunks -eq 0) {
    Write-Host "DIQQAT: bilimlar bazasi yuklanmadi (chunks=0)." -ForegroundColor Red
    exit 1
}
Write-Host "   bilimlar bazasi yuklandi: chunks=$($health.chunks)" -ForegroundColor Green

Write-Host "5/5 Telegram bot ishga tushirilmoqda..." -ForegroundColor Cyan
$env:ASSISTANT_API_URL = "http://127.0.0.1:$Port"
Start-Process -FilePath $Python -WorkingDirectory $Root -ArgumentList "scripts/telegram_polling.py"

Write-Host "Tayyor. Botga yozib sinab ko'ring." -ForegroundColor Green
