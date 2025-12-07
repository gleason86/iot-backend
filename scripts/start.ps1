# Start IoT Backend Services

Write-Host "Starting IoT Backend..." -ForegroundColor Cyan

$projectRoot = Join-Path $PSScriptRoot ".."
Push-Location $projectRoot

try {
    docker compose up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Services started successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Access points:" -ForegroundColor Cyan
        Write-Host "  Grafana:  http://localhost:3000" -ForegroundColor White
        Write-Host "  InfluxDB: http://localhost:8086" -ForegroundColor White
        Write-Host "  MQTT:     localhost:1883" -ForegroundColor White
        Write-Host ""
        Write-Host "View logs: docker compose logs -f" -ForegroundColor Gray
    }
} finally {
    Pop-Location
}


