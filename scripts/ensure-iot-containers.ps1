# Re-starts allow-listed iot containers that Docker Desktop left exited after a
# host reboot (observed 2026-09-15, 2026-09-18 and 2026-09-19: iot-mosquitto
# stays "Exited (255)" while iot-influxdb resumes; see
# docs/docker-desktop-resume-gap-2026-09-20.md). Dry run unless -Apply.
param(
    [switch]$Apply,
    [int]$WaitMinutes = 10,
    [string]$LogPath = (Join-Path $env:LOCALAPPDATA 'iot-backend\ensure-iot-containers.log')
)
$ErrorActionPreference = 'Stop'
# Broker first: iot-telegraf's mqtt_consumer resolves "mosquitto" through
# Docker's embedded DNS, which only answers for a running service.
$containers = @('iot-mosquitto', 'iot-influxdb', 'iot-telegraf')

function Write-Log([string]$message) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK'), $message
    Write-Output $line
    if ($LogPath) {
        New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null
        Add-Content -Path $LogPath -Value $line
    }
}

$deadline = (Get-Date).AddMinutes($WaitMinutes)
while ($true) {
    & docker info *> $null
    if ($LASTEXITCODE -eq 0) { break }
    if ((Get-Date) -gt $deadline) {
        Write-Log "docker engine not ready after $WaitMinutes min; giving up"
        exit 2
    }
    Start-Sleep -Seconds 15
}

$started = 0
$failed = 0
foreach ($name in $containers) {
    $raw = & docker inspect --format '{{.State.Status}} {{.HostConfig.RestartPolicy.Name}}' $name 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) {
        Write-Log "${name}: not found; skipped"
        continue
    }
    $status, $policy = ($raw.Trim() -split ' ', 2)
    if ($status -eq 'running') {
        Write-Log "${name}: running"
        continue
    }
    if ($policy -notin @('unless-stopped', 'always')) {
        Write-Log "${name}: $status with restart policy '$policy'; left alone"
        continue
    }
    if (-not $Apply) {
        Write-Log "${name}: $status; would start (dry run, pass -Apply)"
        continue
    }
    & docker start $name *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Log "${name}: started"
        $started++
    } else {
        Write-Log "${name}: docker start failed (exit $LASTEXITCODE)"
        $failed++
    }
}
Write-Log "done: started=$started failed=$failed apply=$([bool]$Apply)"
if ($failed) { exit 1 }
