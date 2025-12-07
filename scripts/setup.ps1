# IoT Backend Setup Script for Windows
# Run this script to initialize the environment

Write-Host "IoT Backend Setup" -ForegroundColor Cyan
Write-Host "=================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Host "[OK] Docker is running" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Create .env file if it doesn't exist
$envFile = Join-Path $PSScriptRoot "..\\.env"
$envExample = Join-Path $PSScriptRoot "..\\env.example.txt"

if (-not (Test-Path $envFile)) {
    Write-Host ""
    Write-Host "Creating .env file from template..." -ForegroundColor Yellow
    
    # Generate secure passwords
    $mqttPassword = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 24 | ForEach-Object {[char]$_})
    $influxPassword = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 24 | ForEach-Object {[char]$_})
    $influxToken = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 48 | ForEach-Object {[char]$_})
    $grafanaPassword = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 16 | ForEach-Object {[char]$_})
    
    $envContent = @"
# IoT Backend Environment Configuration
# Generated on $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

# =============================================================================
# MQTT (Mosquitto)
# =============================================================================
MQTT_USER=mqtt_user
MQTT_PASSWORD=$mqttPassword

# =============================================================================
# InfluxDB
# =============================================================================
INFLUXDB_ADMIN_USER=admin
INFLUXDB_ADMIN_PASSWORD=$influxPassword
INFLUXDB_ORG=home
INFLUXDB_BUCKET=iot
INFLUXDB_ADMIN_TOKEN=$influxToken

# =============================================================================
# Grafana
# =============================================================================
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$grafanaPassword
"@
    
    $envContent | Out-File -FilePath $envFile -Encoding utf8 -NoNewline
    Write-Host "[OK] Created .env with generated passwords" -ForegroundColor Green
    Write-Host ""
    Write-Host "IMPORTANT: Save these credentials!" -ForegroundColor Yellow
    Write-Host "  MQTT Password: $mqttPassword" -ForegroundColor White
    Write-Host "  Grafana Password: $grafanaPassword" -ForegroundColor White
} else {
    Write-Host "[OK] .env file already exists" -ForegroundColor Green
}

# Create MQTT password file
$mosquittoDir = Join-Path $PSScriptRoot "..\\mosquitto"
$passwordFile = Join-Path $mosquittoDir "password.txt"

if (-not (Test-Path $passwordFile)) {
    Write-Host ""
    Write-Host "Creating MQTT password file..." -ForegroundColor Yellow
    
    # Read MQTT credentials from .env
    $envContent = Get-Content $envFile
    $mqttUser = ($envContent | Where-Object { $_ -match "^MQTT_USER=" }) -replace "MQTT_USER=", ""
    $mqttPass = ($envContent | Where-Object { $_ -match "^MQTT_PASSWORD=" }) -replace "MQTT_PASSWORD=", ""
    
    # Use Docker to generate the password hash
    docker run --rm -v "${mosquittoDir}:/mosquitto/config" eclipse-mosquitto mosquitto_passwd -b -c /mosquitto/config/password.txt $mqttUser $mqttPass
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Created MQTT password file" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Failed to create MQTT password file" -ForegroundColor Red
    }
} else {
    Write-Host "[OK] MQTT password file already exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. cd to iot-backend directory"
Write-Host "  2. Run: docker compose up -d"
Write-Host "  3. Access Grafana at: http://localhost:3000"
Write-Host "  4. Access InfluxDB at: http://localhost:8086"
Write-Host ""


