#Requires -Version 5.1
<#
logging_state for Telegraf on the Ryzen (runs as NT SERVICE\telegraf every 60 s).

One row per Windows Firewall profile (tag profile=domain|private|public, fw=winfw):
  enabled, log_blocked, log_allowed (bool), log_path (expanded), cap_kb (int),
  log_readable (bool: can THIS identity open pfirewall.log for read; true only once
  the log-collector worker's pfirewall-acl.ps1 has granted NT SERVICE\telegraf),
  audit_logon / audit_logoff (string): the "Logon"/"Logoff" audit subcategory
  settings from `auditpol /get /subcategory:... /r`. auditpol needs
  SeSecurityPrivilege: non-elevated and under the virtual service account it fails
  with 0x00000522 ("A required privilege is not held by the client"), so both are
  "unknown (needs elevation)" and audit_error carries the exact text. That is a
  permanent limitation for this collector identity, not a transient one.
#>
[CmdletBinding()] param()
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'lp.ps1')

$ts = Get-NowNs
$lines = @()
$rows = 0

# --- audit policy (best effort; expected to fail without elevation)
$auditLogon = 'unknown (needs elevation)'; $auditLogoff = 'unknown (needs elevation)'; $auditError = ''
foreach ($sub in @('Logon', 'Logoff')) {
    $r = Get-NativeOutput 'auditpol.exe' @('/get', "/subcategory:`"$sub`"", '/r')
    if ($r.exit -eq 0) {
        # CSV: Machine Name,Policy Target,Subcategory,Subcategory GUID,Inclusion Setting,Exclusion Setting
        $row = ($r.stdout -split "`r?`n" | Where-Object { $_ -match "^[^,]*,[^,]*,$sub," } | Select-Object -First 1)
        if ($row) { $setting = ($row -split ',')[4]; if ($sub -eq 'Logon') { $auditLogon = $setting } else { $auditLogoff = $setting } }
    }
    elseif (-not $auditError) {
        $auditError = (($r.stdout + ' ' + $r.stderr) -replace '\s+', ' ').Trim()
        if (-not $auditError) { $auditError = "auditpol exit $($r.exit)" }
    }
}

# --- per-profile firewall logging state
try {
    $profiles = @(Get-NetFirewallProfile -ErrorAction Stop)
    foreach ($p in $profiles) {
        $path = [Environment]::ExpandEnvironmentVariables([string]$p.LogFileName)
        $readable = $false
        try { $fs = [System.IO.File]::Open($path, 'Open', 'Read', 'ReadWrite'); $fs.Close(); $readable = $true } catch { $readable = $false }
        $lines += ('logging_state,fw=winfw,profile=' + (ConvertTo-LpTag ([string]$p.Name).ToLowerInvariant()) +
            ' enabled=' + (ConvertTo-LpBool ([string]$p.Enabled -eq 'True')) +
            ',log_blocked=' + (ConvertTo-LpBool ([string]$p.LogBlocked -eq 'True')) +
            ',log_allowed=' + (ConvertTo-LpBool ([string]$p.LogAllowed -eq 'True')) +
            ',log_path=' + (ConvertTo-LpString $path) +
            ',cap_kb=' + [long]$p.LogMaxSizeKilobytes + 'i' +
            ',log_readable=' + (ConvertTo-LpBool $readable) +
            ',audit_logon=' + (ConvertTo-LpString $auditLogon) +
            ',audit_logoff=' + (ConvertTo-LpString $auditLogoff) +
            ',audit_error=' + (ConvertTo-LpString $auditError) + ' ' + $ts)
        $rows++
    }
    $lines += New-ExecRun 'logging-state' $true $rows '' $ts
}
catch {
    $lines += New-ExecRun 'logging-state' $false $rows ('firewall_profile_query_failed:' + $_.Exception.GetType().Name) $ts
}
Write-LpLines $lines
exit 0
