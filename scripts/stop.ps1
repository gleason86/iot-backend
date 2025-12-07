# Stop IoT Backend Services

Write-Host "Stopping IoT Backend..." -ForegroundColor Cyan

$projectRoot = Join-Path $PSScriptRoot ".."
Push-Location $projectRoot

try {
    docker compose down
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Services stopped." -ForegroundColor Green
    }
} finally {
    Pop-Location
}


