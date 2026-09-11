# Daily backup of the live primary; never promotes or refreshes the cold standby.
$ErrorActionPreference = 'Stop'
if ((Get-TimeZone).Id -ne 'Pacific Standard Time') { throw 'Review Windows timezone before scheduling 03:15.' }
$name = 'IoT Backend Verified Encrypted Recovery'
$python = (Get-Command python).Source
$arguments = '"' + (Join-Path $PSScriptRoot 'daily-recovery.py') + '"'
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Actions.Execute -ne $python -or $existing.Actions.Arguments -ne $arguments) { throw 'Existing task differs; review before replacing.' }
    Write-Output 'Matching daily recovery task already exists.'
    exit 0
}
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At '03:15'
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Online Influx export, isolated restore, encrypted verification and independent Threadripper copy; no cutover.' | Out-Null
Start-ScheduledTask -TaskName $name
Write-Output 'Daily verified recovery task installed and started.'
