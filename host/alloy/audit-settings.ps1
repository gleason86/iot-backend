# Ryzen audit and log settings for the RDP/logon streams (decision D5,
# household observability M3 pilot; A 3.3 source retention).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\audit-settings.ps1 -Mode Preflight   (any user, read-only)
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\audit-settings.ps1 -Mode Apply       (administrator)
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\audit-settings.ps1 -Mode Rollback    (administrator)
#
# Apply (D5a/D5c): auditpol Logon S+F, Logoff S, Other Logon/Logoff Events S+F,
# Account Lockout S+F (no Special Logon); Security log 128 MB; LSM, RCM and
# RdpCoreTS channels 16 MB; firewall packet log cap raised on all three
# profiles to 32767 KB (the cmdlet's maximum; D5c says "32 MB"). LogAllowed
# stays off (D5b). Backups first: auditpol /backup and a JSON of the previous
# sizes. Rollback restores both from the latest backup.
[CmdletBinding()]
param([ValidateSet('Preflight', 'Apply', 'Rollback')][string]$Mode = 'Preflight')
$ErrorActionPreference = 'Stop'

$backupDir = 'C:\ProgramData\GrafanaLabs\Alloy\backups'
# Subcategory GUIDs (locale-independent) in category Logon/Logoff.
$auditSubcategories = @(
    @{ Name = 'Logon';                     Guid = '{0CCE9215-69AE-11D9-BED3-505054503030}'; Success = 'enable'; Failure = 'enable' },
    @{ Name = 'Logoff';                    Guid = '{0CCE9216-69AE-11D9-BED3-505054503030}'; Success = 'enable'; Failure = 'disable' },
    @{ Name = 'Account Lockout';           Guid = '{0CCE9217-69AE-11D9-BED3-505054503030}'; Success = 'enable'; Failure = 'enable' },
    @{ Name = 'Other Logon/Logoff Events'; Guid = '{0CCE921C-69AE-11D9-BED3-505054503030}'; Success = 'enable'; Failure = 'enable' }
)
$logSizes = @{
    'Security'                                                             = 134217728
    'Microsoft-Windows-TerminalServices-LocalSessionManager/Operational'    = 16777216
    'Microsoft-Windows-TerminalServices-RemoteConnectionManager/Operational' = 16777216
    'Microsoft-Windows-RemoteDesktopServices-RdpCoreTS/Operational'         = 16777216
}
$firewallLogKilobytes = 32767
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

function Show-AuditPolicy {
    Write-Output '--- auditpol Logon/Logoff (target: Logon S+F, Logoff S, Other Logon/Logoff Events S+F, Account Lockout S+F) ---'
    # auditpol /get needs SeSecurityPrivilege; non-elevated it fails with 0x522 on stderr.
    $ErrorActionPreference = 'Continue'
    $out = & auditpol.exe /get /category:'Logon/Logoff' 2>&1
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0) {
        $first = ($out | Select-Object -First 1) -replace '\s+', ' '
        Write-Output "  not readable without elevation (auditpol exit ${LASTEXITCODE}: $first)"
        return
    }
    $out | Where-Object { "$_" -match '\S' } | ForEach-Object { Write-Output "  $_" }
}

function Show-LogSizes {
    Write-Output '--- event log sizes (target: Security 128 MB, LSM/RCM/RdpCoreTS 16 MB) ---'
    foreach ($name in $logSizes.Keys) {
        try {
            $l = Get-WinEvent -ListLog $name -ErrorAction Stop
            Write-Output ("  {0}: MaximumSizeInBytes={1} IsEnabled={2} Records={3}" -f $name, $l.MaximumSizeInBytes, $l.IsEnabled, $l.RecordCount)
        } catch { Write-Output "  ${name}: not readable without elevation" }
    }
}

function Show-FirewallLog {
    Write-Output "--- firewall log cap (target: $firewallLogKilobytes KB on Domain, Private, Public; LogAllowed stays False) ---"
    try { Get-NetFirewallProfile | ForEach-Object { Write-Output ("  {0}: LogMaxSizeKilobytes={1} LogBlocked={2} LogAllowed={3}" -f $_.Name, $_.LogMaxSizeKilobytes, $_.LogBlocked, $_.LogAllowed) } }
    catch { Write-Output "  Get-NetFirewallProfile failed: $($_.Exception.Message)" }
}

function Show-Lockout {
    Write-Output '--- account lockout policy (A 8.3 precondition for the attended failed-login test) ---'
    $ErrorActionPreference = 'Continue'
    $out = & net.exe accounts 2>&1
    $ErrorActionPreference = 'Stop'
    $out | Where-Object { "$_" -match 'lockout|Lockout' } | ForEach-Object { Write-Output "  $_" }
}

if ($Mode -eq 'Preflight') {
    Write-Output "=== audit-settings.ps1 Preflight ($(Get-Date -Format s)) ==="
    Write-Output "Elevated: $isAdmin"
    Show-AuditPolicy
    Show-LogSizes
    Show-FirewallLog
    Show-Lockout
    Write-Output '--- Apply would ---'
    Write-Output "  1. auditpol /backup /file:$backupDir\auditpol-before-<stamp>.csv; write sizes-before-<stamp>.json"
    foreach ($s in $auditSubcategories) { Write-Output "  2. auditpol /set /subcategory:$($s.Guid) ($($s.Name)) /success:$($s.Success) /failure:$($s.Failure)" }
    foreach ($name in $logSizes.Keys) { Write-Output "  3. wevtutil sl `"$name`" /ms:$($logSizes[$name])" }
    Write-Output "  4. Set-NetFirewallProfile -Profile Domain,Private,Public -LogMaxSizeKilobytes $firewallLogKilobytes"
    Write-Output '  Rollback would: auditpol /restore from the latest backup; wevtutil sl and Set-NetFirewallProfile back to the recorded sizes.'
    exit 0
}
if (-not $isAdmin) { throw 'Run Apply/Rollback in an administrator PowerShell (Preflight is the non-elevated mode).' }
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Start-Transcript -Path (Join-Path $backupDir "audit-settings-$Mode-$stamp.log") | Out-Null
try {
    if ($Mode -eq 'Rollback') {
        $auditBackup = Get-ChildItem -LiteralPath $backupDir -Filter 'auditpol-before-*.csv' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
        $sizesBackup = Get-ChildItem -LiteralPath $backupDir -Filter 'sizes-before-*.json' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
        if (-not $auditBackup -or -not $sizesBackup) { throw "No backup pair found under $backupDir; nothing restored." }
        & auditpol.exe /restore /file:$($auditBackup.FullName)
        if ($LASTEXITCODE -ne 0) { throw 'auditpol /restore failed' }
        Write-Output "Audit policy restored from $($auditBackup.FullName)"
        $sizes = Get-Content -LiteralPath $sizesBackup.FullName -Raw | ConvertFrom-Json
        foreach ($entry in $sizes.logs) {
            & wevtutil.exe sl "$($entry.name)" /ms:$($entry.bytes)
            if ($LASTEXITCODE -ne 0) { throw "wevtutil sl $($entry.name) failed" }
            Write-Output "Restored $($entry.name) to $($entry.bytes) bytes"
        }
        foreach ($p in $sizes.firewall) {
            Set-NetFirewallProfile -Profile $p.name -LogMaxSizeKilobytes $p.kilobytes
            Write-Output "Restored firewall profile $($p.name) cap to $($p.kilobytes) KB"
        }
        Write-Output 'Rollback complete.'
    } else {
        $auditBackup = Join-Path $backupDir "auditpol-before-$stamp.csv"
        & auditpol.exe /backup /file:$auditBackup
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $auditBackup)) { throw 'auditpol /backup failed; no change applied.' }
        $before = [ordered]@{ logs = @(); firewall = @() }
        foreach ($name in $logSizes.Keys) {
            $l = Get-WinEvent -ListLog $name -ErrorAction Stop
            $before.logs += [ordered]@{ name = $name; bytes = $l.MaximumSizeInBytes }
        }
        foreach ($p in Get-NetFirewallProfile) { $before.firewall += [ordered]@{ name = $p.Name; kilobytes = $p.LogMaxSizeKilobytes } }
        $sizesBackup = Join-Path $backupDir "sizes-before-$stamp.json"
        ($before | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $sizesBackup -Encoding ASCII
        Write-Output "Backups: $auditBackup, $sizesBackup"
        Write-Output '--- before ---'
        Show-AuditPolicy; Show-LogSizes; Show-FirewallLog

        foreach ($s in $auditSubcategories) {
            & auditpol.exe /set /subcategory:$($s.Guid) /success:$($s.Success) /failure:$($s.Failure)
            if ($LASTEXITCODE -ne 0) { throw "auditpol /set $($s.Name) failed" }
        }
        foreach ($name in $logSizes.Keys) {
            & wevtutil.exe sl "$name" /ms:$($logSizes[$name])
            if ($LASTEXITCODE -ne 0) { throw "wevtutil sl $name failed" }
        }
        Set-NetFirewallProfile -Profile Domain, Private, Public -LogMaxSizeKilobytes $firewallLogKilobytes

        Write-Output '--- after ---'
        Show-AuditPolicy; Show-LogSizes; Show-FirewallLog
        Write-Output 'Applied. Security 4624/4625/4634/4647/4778/4779/4800/4801 now audit; verify with an attended RDP logon and the winsec stream in Loki.'
    }
} finally { Stop-Transcript | Out-Null }
