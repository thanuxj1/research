# LostinSriLanka — start all services
# Run from E:\research with: powershell -ExecutionPolicy Bypass -File start.ps1

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

function Kill-Port($port) {
    $pids = (netstat -ano | Select-String ":$port\s.*LISTENING") -replace '.*LISTENING\s+', '' | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^\d+$' }
    foreach ($p in $pids) {
        try { Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue } catch {}
    }
}

Write-Host "Stopping any existing services..."
Kill-Port 8090
Kill-Port 8001
Start-Sleep -Seconds 1

Write-Host ""
Write-Host "Starting Backend — Gateway on http://localhost:8090 ..."
Start-Process -FilePath "python" -ArgumentList "$ROOT\gateway.py --port 8090" -WorkingDirectory $ROOT -WindowStyle Normal

Start-Sleep -Seconds 2

Write-Host "Starting Food AI backend on port 8001 ..."
Start-Process -FilePath "python" -ArgumentList "-m uvicorn main:app --host 127.0.0.1 --port 8001" -WorkingDirectory "$ROOT\food-assistant\backend" -WindowStyle Normal

Write-Host ""
Write-Host "========================================"
Write-Host "  Open: http://localhost:8090/"
Write-Host ""
Write-Host "  Reviews (Map + Analytics)  ->  /travellens/"
Write-Host "  AI Assistant               ->  /ai/"
Write-Host "  Food Guide                 ->  /food/"
Write-Host "========================================"
Write-Host "(Food AI loads its ML model in ~15 sec on first start)"
