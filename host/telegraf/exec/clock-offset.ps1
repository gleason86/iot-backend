#Requires -Version 5.1
<#
clock_offset for Telegraf on the Ryzen (runs as NT SERVICE\telegraf every 60 s).

`w32tm /query /status /verbose` (no elevation needed). Fields:
  offset_s   (float) "Phase Offset" in seconds as w32tm reports it (the residual the
             clock discipline is correcting; only present in /verbose output)
  source     (string) "w32time:<Source line>", e.g. w32time:time.windows.com,0x9
  synced     (bool) stratum 1..15, leap indicator 0 and a recorded last successful sync
  last_sync_age_s (float, additive) "Time since Last Good Sync Time"
  last_sync_error (string, additive) the "Last Sync Error" text (e.g. stale time data)
A missing Phase Offset line leaves offset_s out (never 0.0) and marks exec_run ok=false.
#>
[CmdletBinding()] param()
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'lp.ps1')

$ts = Get-NowNs
$r = Get-NativeOutput 'w32tm.exe' @('/query', '/status', '/verbose')
if ($r.exit -ne 0) {
    Write-LpLines @((New-ExecRun 'clock-offset' $false 0 ("w32tm_exit_$($r.exit)") $ts))
    exit 0
}
$values = @{}
foreach ($line in ($r.stdout -split "`r?`n")) {
    $key, $rest = $line -split ':', 2
    if ($null -ne $rest) { $values[$key.Trim()] = $rest.Trim() }
}
$inv = [System.Globalization.CultureInfo]::InvariantCulture
$offset = $null
if ($values['Phase Offset'] -match '^(-?\d+(?:\.\d+)?)s$') { $offset = [double]::Parse($Matches[1], $inv) }
$stratum = 0; if ($values['Stratum'] -match '^(\d+)') { $stratum = [int]$Matches[1] }
$leap = 0; if ($values['Leap Indicator'] -match '^(\d+)') { $leap = [int]$Matches[1] }
$lastSync = [string]$values['Last Successful Sync Time']
$synced = ($stratum -ge 1 -and $stratum -le 15 -and $leap -ne 3 -and $lastSync -and $lastSync -ne 'unspecified')
$source = 'w32time:' + [string]$values['Source']
$age = $null
if ($values['Time since Last Good Sync Time'] -match '^(-?\d+(?:\.\d+)?)s$') { $age = [double]::Parse($Matches[1], $inv) }
$syncError = [string]$values['Last Sync Error']

$fields = @()
if ($null -ne $offset) { $fields += 'offset_s=' + (ConvertTo-LpFloat $offset) }
$fields += 'source=' + (ConvertTo-LpString $source)
$fields += 'synced=' + (ConvertTo-LpBool $synced)
if ($null -ne $age) { $fields += 'last_sync_age_s=' + (ConvertTo-LpFloat $age) }
$fields += 'last_sync_error=' + (ConvertTo-LpString $syncError)
$lines = @('clock_offset ' + ($fields -join ',') + ' ' + $ts)
$lines += New-ExecRun 'clock-offset' ($null -ne $offset) 1 $(if ($null -eq $offset) { 'no_phase_offset_line' } else { '' }) $ts
Write-LpLines $lines
exit 0
