# IoT Backend Troubleshooting Script
Write-Host "IoT Backend Stack Troubleshooting" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Initialize diagnostics
$diagnostics = @{
    services = @()
    issues = @()
    recommendations = @()
}

# Function to check service health
function Test-ServiceHealth {
    param([string]$ServiceName, [string]$ContainerName)

    Write-Host "Checking $ServiceName..." -ForegroundColor Yellow

    try {
        $containerStatus = docker compose ps $ContainerName --format "table {{.Name}}\t{{.Status}}" 2>$null | Select-Object -Skip 1
    } catch {
        $containerStatus = $null
    }

    if ($containerStatus -and $containerStatus -match "Up") {
        Write-Host "  [+] Container running" -ForegroundColor Green
        $diagnostics.services += @{name=$ServiceName; status="running"}
    } elseif ($containerStatus -and $containerStatus -match "restarting|unhealthy") {
        Write-Host "  [-] Container unhealthy" -ForegroundColor Red
        $diagnostics.services += @{name=$ServiceName; status="unhealthy"}
        $diagnostics.issues += "$ServiceName container is unhealthy"
        $diagnostics.recommendations += "Check logs: docker compose logs $ContainerName"
    } else {
        Write-Host "  [-] Container not running" -ForegroundColor Red
        $diagnostics.services += @{name=$ServiceName; status="stopped"}
        $diagnostics.issues += "$ServiceName container is not running"
        $diagnostics.recommendations += "Start service: docker compose up -d $ContainerName"
    }

    Write-Host ""
}

# Check Docker availability
try {
    $dockerVersion = docker --version 2>$null
    Write-Host "[+] Docker available" -ForegroundColor Green
} catch {
    Write-Host "[-] Docker not available" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Test core services
Test-ServiceHealth -ServiceName "Mosquitto" -ContainerName "mosquitto"
Test-ServiceHealth -ServiceName "InfluxDB" -ContainerName "influxdb"
Test-ServiceHealth -ServiceName "Grafana" -ContainerName "grafana"
Test-ServiceHealth -ServiceName "Telegraf" -ContainerName "telegraf"

# Summary
Write-Host "Diagnostic Summary" -ForegroundColor Cyan
Write-Host "=================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Services Status:" -ForegroundColor White
$diagnostics.services | ForEach-Object {
    $statusColor = switch ($_.status) {
        "running" { "Green" }
        "unhealthy" { "Red" }
        "stopped" { "Red" }
        default { "Yellow" }
    }
    Write-Host "  $($_.name): " -NoNewline
    Write-Host "$($_.status)" -ForegroundColor $statusColor
}

if ($diagnostics.issues.Count -gt 0) {
    Write-Host ""
    Write-Host "Issues Found:" -ForegroundColor Red
    $diagnostics.issues | ForEach-Object {
        Write-Host "  - $_" -ForegroundColor Red
    }
}

if ($diagnostics.recommendations.Count -gt 0) {
    Write-Host ""
    Write-Host "Recommendations:" -ForegroundColor Yellow
    $diagnostics.recommendations | ForEach-Object {
        Write-Host "  - $_" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Quick Fix Commands:" -ForegroundColor Cyan
Write-Host "  Restart all services: docker compose restart" -ForegroundColor White
Write-Host "  View all logs: docker compose logs -f" -ForegroundColor White
Write-Host "  Rebuild services: docker compose up -d --build" -ForegroundColor White
Write-Host "  Clean restart: docker compose down; docker compose up -d" -ForegroundColor White

Write-Host ""
Write-Host "Troubleshooting complete!" -ForegroundColor Green