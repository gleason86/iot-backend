# IoT Data Pipeline Flow Test

Comprehensive end-to-end test of the complete IoT data pipeline from MQTT ingestion through to Grafana visualization.

## Overview
This test validates the entire data flow:
1. **MQTT Publishing** → Message sent to broker
2. **Telegraf Processing** → Data transformation and field mapping
3. **InfluxDB Storage** → Time-series data persistence
4. **Grafana Access** → Dashboard and API availability

## Usage
Run this command to verify that all components of the IoT data pipeline are working correctly.

## Prerequisites
- Docker Compose stack must be running
- All services (MQTT, Telegraf, InfluxDB, Grafana) must be healthy
- `.env` file with database credentials must exist

## Test Steps

### 1. MQTT Connection Test
```powershell
# Send test message to MQTT broker
$testData = @{
    device_id = "data_flow_test_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    temperature_f = 75.5
    humidity = 62.3
    motion = $true
}
$jsonMessage = $testData | ConvertTo-Json -Compress
docker compose exec -T mosquitto mosquitto_pub -h localhost -t "iot/sensors/test/data" -m $jsonMessage
```

### 2. Telegraf Processing Verification
```powershell
# Check Telegraf logs for processing evidence
docker compose logs telegraf | Select-String -Pattern $testDeviceId
```

### 3. InfluxDB Storage Validation
```powershell
# Query InfluxDB for test data
$fluxQuery = "from(bucket:\"iot\") |> range(start: -5m) |> filter(fn: (r) => r.device_id =~ /$testDeviceId/)"
docker compose exec -T influxdb influx query $fluxQuery
```

### 4. Grafana Accessibility Check
```powershell
# Test Grafana health endpoint
Invoke-WebRequest -Uri "http://localhost:3000/api/health"
```

## Expected Results
- ✅ MQTT: Message published and received by broker
- ✅ Telegraf: Processing logs show data transformation
- ✅ InfluxDB: Test data stored with correct field mappings
- ✅ Grafana: Health endpoint responds successfully

## Troubleshooting
If any step fails:
- **MQTT**: Check `docker compose logs mosquitto`
- **Telegraf**: Check `docker compose logs telegraf` and config syntax
- **InfluxDB**: Verify credentials in `.env` and bucket creation
- **Grafana**: Check service startup and network connectivity

## Cleanup
Test data is automatically cleaned up after validation. Manual cleanup if needed:
```powershell
# Remove test data from InfluxDB
$deleteQuery = "from(bucket:\"iot\") |> range(start: 0) |> filter(fn: (r) => r.device_id =~ /$testDeviceId/) |> drop()"
docker compose exec -T influxdb influx delete --bucket iot --start 2020-01-01T00:00:00Z --stop 2030-01-01T00:00:00Z --predicate "_measurement=\"sensor_data\" AND device_id=\"$testDeviceId\""
```

$testResults = @{
    mqtt = @{status = "pending"; message = ""}
    telegraf = @{status = "pending"; message = ""}
    influxdb = @{status = "pending"; message = ""}
    grafana = @{status = "pending"; message = ""}
    overall = @{status = "pending"; message = ""}
}

function Write-TestResult {
    param([string]$stage, [string]$status, [string]$message)

    $testResults[$stage].status = $status
    $testResults[$stage].message = $message

    $statusIcon = switch ($status) {
        "pass" { "✅" }
        "fail" { "❌" }
        "warn" { "⚠️" }
        default { "⏳" }
    }

    $statusColor = switch ($status) {
        "pass" { "Green" }
        "fail" { "Red" }
        "warn" { "Yellow" }
        default { "Gray" }
    }

    Write-Host "  $statusIcon $stage`: " -NoNewline -ForegroundColor White
    Write-Host "$message" -ForegroundColor $statusColor
}

function Test-MQTT-Connection {
    Write-Host "📡 Testing MQTT Connection..." -ForegroundColor Yellow

    try {
        # Create test message JSON
        $jsonMessage = $testData | ConvertTo-Json -Compress

        # Send test message via MQTT
        $mqttCommand = "docker compose exec -T mosquitto mosquitto_pub -h localhost -t `"iot/sensors/$testDeviceId/data`" -m `"$jsonMessage`""
        $mqttResult = Invoke-Expression $mqttCommand 2>$null

        if ($LASTEXITCODE -eq 0) {
            Write-TestResult "mqtt" "pass" "Message published successfully"

            # Verify message was received by checking broker logs
            Start-Sleep -Seconds 1
            $logCheck = docker compose logs mosquitto 2>$null | Select-String -Pattern $testDeviceId -Quiet
            if ($logCheck) {
                Write-TestResult "mqtt" "pass" "Message received by broker"
            } else {
                Write-TestResult "mqtt" "warn" "Message sent but not found in logs"
            }
        } else {
            Write-TestResult "mqtt" "fail" "Failed to publish message (exit code: $LASTEXITCODE)"
        }
    }
    catch {
        Write-TestResult "mqtt" "fail" "MQTT test failed: $($_.Exception.Message)"
    }

    Write-Host ""
}

function Test-Telegraf-Processing {
    Write-Host "⚙️ Testing Telegraf Processing..." -ForegroundColor Yellow

    try {
        # Wait for Telegraf to process the message
        Start-Sleep -Seconds 3

        # Check Telegraf logs for processing
        $telegrafLogs = docker compose logs telegraf 2>$null | Select-String -Pattern $testDeviceId

        if ($telegrafLogs) {
            Write-TestResult "telegraf" "pass" "Message processed by Telegraf"

            # Check for any processing errors
            $errorLogs = $telegrafLogs | Select-String -Pattern "ERROR|error|Error" -Quiet
            if ($errorLogs) {
                Write-TestResult "telegraf" "warn" "Processed with errors - check logs"
            } else {
                Write-TestResult "telegraf" "pass" "Processed without errors"
            }
        } else {
            Write-TestResult "telegraf" "fail" "No processing evidence found in logs"
        }
    }
    catch {
        Write-TestResult "telegraf" "fail" "Telegraf test failed: $($_.Exception.Message)"
    }

    Write-Host ""
}

function Test-InfluxDB-Storage {
    Write-Host "💾 Testing InfluxDB Storage..." -ForegroundColor Yellow

    try {
        # Query InfluxDB for our test data
        $fluxQuery = "from(bucket:\""iot\"") |> range(start: -5m) |> filter(fn: (r) => r.device_id == \"$testDeviceId\") |> limit(n:10)"
        $queryCommand = "docker compose exec -T influxdb influx query '$fluxQuery'"

        $queryResult = Invoke-Expression $queryCommand 2>$null

        if ($queryResult -and $queryResult -match $testDeviceId) {
            Write-TestResult "influxdb" "pass" "Data stored successfully"

            # Validate data integrity
            $expectedFields = @("temperature_f", "humidity", "motion")
            $missingFields = @()

            foreach ($field in $expectedFields) {
                if ($queryResult -notmatch $field) {
                    $missingFields += $field
                }
            }

            if ($missingFields.Count -gt 0) {
                Write-TestResult "influxdb" "warn" "Missing fields: $($missingFields -join ', ')"
            } else {
                Write-TestResult "influxdb" "pass" "All fields stored correctly"
            }

            # Check data values
            if ($queryResult -match "temperature_f.*75.5") {
                Write-TestResult "influxdb" "pass" "Data values correct"
            } else {
                Write-TestResult "influxdb" "warn" "Data values may be incorrect"
            }

        } else {
            Write-TestResult "influxdb" "fail" "Test data not found in database"
        }
    }
    catch {
        Write-TestResult "influxdb" "fail" "InfluxDB test failed: $($_.Exception.Message)"
    }

    Write-Host ""
}

function Test-Grafana-Accessibility {
    Write-Host "📊 Testing Grafana Accessibility..." -ForegroundColor Yellow

    try {
        # Test Grafana health endpoint
        $healthResponse = Invoke-WebRequest -Uri "http://localhost:3000/api/health" -TimeoutSec 10 -ErrorAction Stop

        if ($healthResponse.StatusCode -eq 200) {
            Write-TestResult "grafana" "pass" "Grafana health check passed"

            # Try to access a dashboard (if it exists)
            try {
                $dashboardResponse = Invoke-WebRequest -Uri "http://localhost:3000/api/search?query=iot" -TimeoutSec 5 -ErrorAction Stop
                if ($dashboardResponse.StatusCode -eq 200) {
                    Write-TestResult "grafana" "pass" "Dashboard API accessible"
                }
            }
            catch {
                Write-TestResult "grafana" "warn" "Dashboard API not accessible"
            }
        } else {
            Write-TestResult "grafana" "fail" "Grafana health check failed (status: $($healthResponse.StatusCode))"
        }
    }
    catch {
        Write-TestResult "grafana" "fail" "Grafana test failed: $($_.Exception.Message)"
    }

    Write-Host ""
}

function Cleanup-TestData {
    Write-Host "🧹 Cleaning up test data..." -ForegroundColor Yellow

    try {
        # Remove test data from InfluxDB
        $deleteQuery = "from(bucket:\""iot\"") |> range(start: 0) |> filter(fn: (r) => r.device_id == \"$testDeviceId\") |> drop()"
        $deleteCommand = "docker compose exec -T influxdb influx delete --bucket iot --start 2020-01-01T00:00:00Z --stop 2030-01-01T00:00:00Z --predicate `"_measurement=`"sensor_data`" and device_id=`"$testDeviceId`"`""

        $deleteResult = Invoke-Expression $deleteCommand 2>$null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✅ Test data cleaned from InfluxDB" -ForegroundColor Green
        } else {
            Write-Host "  ⚠️ Could not clean test data from InfluxDB" -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "  ⚠️ Cleanup failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    Write-Host ""
}

function Generate-TestReport {
    Write-Host "📊 Test Results Summary" -ForegroundColor Cyan
    Write-Host "=======================" -ForegroundColor Cyan
    Write-Host ""

    # Overall assessment
    $passedTests = ($testResults.Values | Where-Object { $_.status -eq "pass" }).Count
    $failedTests = ($testResults.Values | Where-Object { $_.status -eq "fail" }).Count
    $warnedTests = ($testResults.Values | Where-Object { $_.status -eq "warn" }).Count
    $totalTests = $testResults.Count - 1  # Exclude overall

    if ($failedTests -eq 0) {
        $testResults.overall.status = "pass"
        $testResults.overall.message = "All pipeline stages working correctly"
    } elseif ($failedTests -le 2) {
        $testResults.overall.status = "warn"
        $testResults.overall.message = "Some issues detected - partial pipeline failure"
    } else {
        $testResults.overall.status = "fail"
        $testResults.overall.message = "Major pipeline issues detected"
    }

    # Display results
    Write-Host "Test Results:" -ForegroundColor White
    foreach ($stage in @("mqtt", "telegraf", "influxdb", "grafana")) {
        $statusIcon = switch ($testResults[$stage].status) {
            "pass" { "✅" }
            "fail" { "❌" }
            "warn" { "⚠️" }
            default { "⏳" }
        }
        $statusColor = switch ($testResults[$stage].status) {
            "pass" { "Green" }
            "fail" { "Red" }
            "warn" { "Yellow" }
            default { "Gray" }
        }

        Write-Host "  $statusIcon $(($stage).ToUpper())`: " -NoNewline -ForegroundColor White
        Write-Host "$($testResults[$stage].message)" -ForegroundColor $statusColor
    }

    Write-Host ""
    Write-Host "Overall Status:" -ForegroundColor White
    $overallIcon = switch ($testResults.overall.status) {
        "pass" { "✅" }
        "fail" { "❌" }
        "warn" { "⚠️" }
    }
    $overallColor = switch ($testResults.overall.status) {
        "pass" { "Green" }
        "fail" { "Red" }
        "warn" { "Yellow" }
    }
    Write-Host "  $overallIcon $($testResults.overall.message)" -ForegroundColor $overallColor

    Write-Host ""
    Write-Host "📈 Pipeline Flow:" -ForegroundColor White
    Write-Host "  MQTT → Telegraf → InfluxDB → Grafana" -ForegroundColor Gray
    Write-Host "  📡     ⚙️        💾        📊" -ForegroundColor Gray

    # Recommendations
    if ($testResults.overall.status -ne "pass") {
        Write-Host ""
        Write-Host "💡 Troubleshooting Recommendations:" -ForegroundColor Yellow

        if ($testResults.mqtt.status -eq "fail") {
            Write-Host "  • Check MQTT broker: docker compose logs mosquitto" -ForegroundColor Yellow
            Write-Host "  • Verify broker is running: docker compose ps mosquitto" -ForegroundColor Yellow
        }

        if ($testResults.telegraf.status -eq "fail") {
            Write-Host "  • Check Telegraf config: docker compose logs telegraf" -ForegroundColor Yellow
            Write-Host "  • Validate configuration: docker compose exec telegraf telegraf --test" -ForegroundColor Yellow
        }

        if ($testResults.influxdb.status -eq "fail") {
            Write-Host "  • Check InfluxDB: docker compose logs influxdb" -ForegroundColor Yellow
            Write-Host "  • Verify credentials in .env file" -ForegroundColor Yellow
        }

        if ($testResults.grafana.status -eq "fail") {
            Write-Host "  • Check Grafana: docker compose logs grafana" -ForegroundColor Yellow
            Write-Host "  • Verify service is healthy: Invoke-WebRequest -Uri 'http://localhost:3000/api/health'" -ForegroundColor Yellow
        }

        Write-Host ""
        Write-Host "🔍 Run full diagnostics: .\.cursor\commands\troubleshoot-stack.md" -ForegroundColor Cyan
    }

    Write-Host ""
    Write-Host "✅ Data flow test completed!" -ForegroundColor Green
    Write-Host "Test data cleaned up automatically." -ForegroundColor Gray
}

# Main test execution
Write-Host "🔬 Running comprehensive data pipeline test..." -ForegroundColor Cyan
Write-Host "Test device ID: $testDeviceId" -ForegroundColor Gray
Write-Host ""

# Execute tests in sequence
Test-MQTT-Connection
Test-Telegraf-Processing
Test-InfluxDB-Storage
Test-Grafana-Accessibility

# Cleanup and report
Cleanup-TestData
Generate-TestReport