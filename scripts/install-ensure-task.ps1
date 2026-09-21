# Registers a logon-triggered task that runs ensure-iot-containers.ps1 -Apply
# two minutes after sign-in. Docker Desktop on this PC is a user-session app,
# so containers can only come back once the user logs in; this covers the ones
# its own restart-policy handling leaves exited.
$ErrorActionPreference = 'Stop'
$name = 'IoT Backend Ensure Containers'
$shell = (Get-Command powershell.exe).Source
$script = Join-Path $PSScriptRoot 'ensure-iot-containers.ps1'
$arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $script + '" -Apply'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Actions.Execute -ne $shell -or $existing.Actions.Arguments -ne $arguments) { throw 'Existing task differs; review before replacing.' }
    Write-Output 'Matching ensure-containers task already exists.'
    exit 0
}
$action = New-ScheduledTaskAction -Execute $shell -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = 'PT2M'
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Starts iot-mosquitto/iot-influxdb/iot-telegraf if Docker Desktop left them exited after a reboot; log in %LOCALAPPDATA%\iot-backend.' | Out-Null
Write-Output "Installed '$name' (at logon of $user, 2 min delay). Run it now with: Start-ScheduledTask -TaskName '$name'"
