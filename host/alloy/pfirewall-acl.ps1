# Read ACL on the Windows Firewall packet log for the collector service
# accounts (household observability M3 pilot, CONTRACT.md / A 3.3, 7; D6;
# Codex C3 2026-09-16).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\pfirewall-acl.ps1 -Mode Preflight   (any user, read-only)
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\pfirewall-acl.ps1 -Mode Verify      (any user, read-only; run after a rotation)
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\pfirewall-acl.ps1 -Mode Apply       (administrator)
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\pfirewall-acl.ps1 -Mode Rollback    (administrator)
#
# Apply saves the current ACLs of %SystemRoot%\System32\LogFiles\Firewall
# (icacls /save, recursive) and then grants READ to NT SERVICE\Alloy (log
# collector) and NT SERVICE\telegraf (host-telemetry worker, source_progress)
# on the directory (inheritable) and on both log files. Grants are by service
# SID (sc.exe showsid); icacls can only map a service SID once that service is
# registered (2026-09-17 live finding: error 1332 "No mapping between account
# names and security IDs" for NT SERVICE\telegraf before install-telegraf.ps1
# had run), so Apply grants the services that exist, warns about the absent
# ones, and is re-run after their install (add-only, idempotent). No existing
# ACE is changed. Rollback restores the saved ACLs (or removes the two SIDs
# when no backup is found).
#
# What is observed and what is predicted (Codex C3): both log files carry a
# protected DACL (no inheritance) authored by mpssvc - SYSTEM, Administrators,
# Network Configuration Operators, NT SERVICE\mpssvc - so the directory's
# inheritable ACE does not reach them (OBSERVED 2026-09-16). The explicit file
# grant Apply adds is PREDICTED to disappear when mpssvc creates the next
# pfirewall.log at rotation; that has NOT been observed yet. -Mode Verify is
# the read-only check that settles it: run it after the first rotation that
# follows Apply. Only if Verify shows the Alloy SID without read on the new
# file AND the winfw positions not advancing is the LocalSystem fallback
# (install-alloy.ps1 -RuntimeAccount LocalSystem -Evidence <Verify transcript>)
# in scope. Network Configuration Operators membership and WFP collection are
# not options (C3).
[CmdletBinding()]
param([ValidateSet('Preflight', 'Verify', 'Apply', 'Rollback')][string]$Mode = 'Preflight')
$ErrorActionPreference = 'Stop'

$logDir = Join-Path $env:SystemRoot 'System32\LogFiles\Firewall'
$logFile = Join-Path $logDir 'pfirewall.log'
$logFiles = @($logFile, (Join-Path $logDir 'pfirewall.log.old'))
$services = @('Alloy', 'telegraf')
$alloyProgramData = 'C:\ProgramData\GrafanaLabs\Alloy'
$alloyConfig = Join-Path $alloyProgramData 'config.alloy'
$alloyData = Join-Path $alloyProgramData 'data'
$repoConfig = Join-Path $PSScriptRoot 'config.alloy'
$backupDir = Join-Path $alloyProgramData 'backups'
$systemSid = 'S-1-5-18'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

function Get-ServiceSid {
    param([string]$Name)
    $ErrorActionPreference = 'Continue'
    $out = & sc.exe showsid $Name 2>&1
    $ErrorActionPreference = 'Stop'
    $line = $out | Where-Object { $_ -match 'SERVICE SID:\s*(S-1-5-80-\S+)' } | Select-Object -First 1
    if (-not $line) { throw "sc.exe showsid $Name did not return a SID" }
    return $Matches[1]
}

function Show-Acl {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { Write-Output "  ${Path}: absent"; return }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer) { Write-Output ("  {0}: {1} bytes, modified {2}" -f $Path, $item.Length, $item.LastWriteTime.ToString('s')) }
    else { Write-Output "  ${Path}:" }
    try {
        $acl = Get-Acl -LiteralPath $Path
        Write-Output "    Owner: $($acl.Owner); protected DACL (no inheritance): $($acl.AreAccessRulesProtected)"
        $acl.Access | ForEach-Object { Write-Output ("    ACE {0} {1} {2} inherited={3} flags={4}" -f $_.IdentityReference, $_.AccessControlType, $_.FileSystemRights, $_.IsInherited, $_.InheritanceFlags) }
    } catch { Write-Output '    ACL not readable without elevation' }
}

function Test-SidRead {
    # Does an Allow ACE for $Sid on $Path carry ReadData (or a generic read)? Returns $true/$false, or $null when the ACL is unreadable.
    param([string]$Path, [string]$Sid)
    try { $acl = Get-Acl -LiteralPath $Path } catch { return $null }
    foreach ($r in $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) {
        if ($r.AccessControlType -ne 'Allow' -or $r.IdentityReference.Value -ne $Sid) { continue }
        $v = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$r.FileSystemRights), 0)
        if (($v -band [uint32]1) -or ($v -band [uint32]0x80000000) -or ($v -band [uint32]0x10000000)) { return $true }   # ReadData | GENERIC_READ | GENERIC_ALL
    }
    return $false
}

function Read-Positions([string]$text) {
    # go-yaml complex-key layout ("? path: X" / "labels: Y" / ": value"); same parser as
    # iot-backend/host/telegraf/exec/source-progress.ps1 (kept local: no cross-script dot-sourcing).
    $entries = @{}
    $path = $null
    foreach ($raw in ($text -split "`r?`n")) {
        $line = $raw.Trim()
        if (-not $line -or $line -eq 'positions:' -or $line.StartsWith('#')) { continue }
        if ($line.StartsWith('? ')) { $path = $null; $line = $line.Substring(2).Trim() }
        if ($line.StartsWith('path:')) { $path = Unquote $line.Substring(5) }
        elseif ($line.StartsWith('labels:')) { }
        elseif ($line.StartsWith(':')) { if ($null -ne $path) { $entries[$path] = Unquote $line.Substring(1) }; $path = $null }
        elseif ($line.Contains(':') -and $null -eq $path) { $k, $v = $line -split ':', 2; $entries[(Unquote $k)] = Unquote $v }
    }
    return $entries
}
function Unquote([string]$v) { $v = $v.Trim(); if ($v.Length -ge 2 -and $v[0] -eq $v[-1] -and ($v[0] -eq '"' -or $v[0] -eq "'")) { $v = $v.Substring(1, $v.Length - 2) }; return $v }

function Get-WinfwSourceLabels {
    # The loki.source.file label(s) whose targets include pfirewall.log, from the installed config
    # (or the repo copy when nothing is installed). Determines data\loki.source.file.<label>\positions.yml.
    $cfg = if (Test-Path -LiteralPath $alloyConfig) { $alloyConfig } elseif (Test-Path -LiteralPath $repoConfig) { $repoConfig } else { return @() }
    $text = [System.IO.File]::ReadAllText($cfg)
    $labels = @()
    foreach ($m in [regex]::Matches($text, 'loki\.source\.file\s+"([^"]+)"\s*\{(.*?)\n\}', 'Singleline')) {
        $label = $m.Groups[1].Value
        $body = $m.Groups[2].Value
        if ($body -match 'local\.file_match\.(\w+)\.targets') {
            $fm = $Matches[1]
            $fmBlock = [regex]::Match($text, 'local\.file_match\s+"' + [regex]::Escape($fm) + '"\s*\{(.*?)\n\}', 'Singleline')
            if ($fmBlock.Success -and ($fmBlock.Groups[1].Value -match '(?m)^\s*\{__path__\s*=\s*"[^"]*pfirewall\.log"')) { $labels += $label }
        }
    }
    return $labels
}

function Get-DirState {
    # 'absent' | 'readable' | 'access-denied' | 'error:<type>'. After install-alloy.ps1 -RuntimeAccount
    # LocalSystem the ProgramData tree is SYSTEM/Administrators only, so a non-elevated Verify must
    # report that as unreadable, never as "absent" or "no Apply recorded".
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 'absent' }
    try { Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop | Out-Null; return 'readable' }
    catch [System.UnauthorizedAccessException] { return 'access-denied' }
    catch { return 'error:' + $_.Exception.GetType().Name }
}

function Show-Verify {
    Write-Output "=== pfirewall-acl.ps1 Verify ($(Get-Date -Format s); read-only) ==="
    Write-Output "Elevated: $isAdmin; running as $([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
    $sids = @{}
    foreach ($s in $services) {
        $svc = Get-Service -Name $s -ErrorAction SilentlyContinue
        $present = if ($svc) { "present ($($svc.Status))" } else { 'absent' }
        try { $sids[$s] = Get-ServiceSid $s } catch { $sids[$s] = $null }
        $cim = if ($svc) { Get-CimInstance Win32_Service -Filter "Name='$s'" -ErrorAction SilentlyContinue } else { $null }
        Write-Output "Service ${s}: $present; StartName=$(if ($cim) { $cim.StartName } else { '-' }); virtual account NT SERVICE\$s SID $(if ($sids[$s]) { $sids[$s] } else { 'n/a' })"
    }
    Write-Output '--- current DACLs (directory, pfirewall.log, pfirewall.log.old) ---'
    Show-Acl $logDir
    foreach ($f in $logFiles) { Show-Acl $f }
    Write-Output '--- read access by SID (Allow ACE carrying ReadData / generic read) ---'
    foreach ($p in @($logDir) + $logFiles) {
        if (-not (Test-Path -LiteralPath $p)) { Write-Output "  ${p}: absent"; continue }
        $parts = @()
        foreach ($s in $services) {
            $r = if ($sids[$s]) { Test-SidRead $p $sids[$s] } else { $null }
            $parts += "NT SERVICE\$s=" + $(if ($null -eq $r) { 'unreadable-acl' } else { $r })
        }
        $sys = Test-SidRead $p $systemSid
        $parts += 'SYSTEM=' + $(if ($null -eq $sys) { 'unreadable-acl' } else { $sys })
        Write-Output "  ${p}: $($parts -join '; ')"
    }
    Write-Output '--- file times (UTC) ---'
    $rotationMarker = $null
    foreach ($f in $logFiles) {
        if (-not (Test-Path -LiteralPath $f)) { Write-Output "  ${f}: absent"; continue }
        $i = Get-Item -LiteralPath $f -Force
        $created = $i.CreationTimeUtc.ToString('s') + 'Z'
        $modified = $i.LastWriteTimeUtc.ToString('s') + 'Z'
        Write-Output ("  {0}: created {1}, modified {2}, {3} bytes" -f $f, $created, $modified, $i.Length)
        if ($f -like '*.old') { $rotationMarker = $i.LastWriteTimeUtc }
    }
    Write-Output '  Rotation marker = pfirewall.log.old LastWriteTimeUtc (the moment mpssvc renamed the full log). pfirewall.log'
    Write-Output '  CreationTime can be inherited from the renamed file by NTFS name tunneling (15 s window), so it is not trusted alone.'
    if ($rotationMarker) { Write-Output "  Last rotation (marker): $($rotationMarker.ToString('s'))Z" } else { Write-Output '  Last rotation: unknown (no pfirewall.log.old)' }
    Write-Output '--- Alloy winfw positions (has the tailer advanced since the last rotation?) ---'
    $labels = @(Get-WinfwSourceLabels)
    if ($labels.Count -eq 0) { Write-Output "  no loki.source.file targeting pfirewall.log found in $alloyConfig / $repoConfig" }
    $logSize = if (Test-Path -LiteralPath $logFile) { (Get-Item -LiteralPath $logFile -Force).Length } else { $null }
    $verdictAdvanced = $null
    $dataState = Get-DirState $alloyData
    foreach ($label in $labels) {
        $pos = Join-Path $alloyData "loki.source.file.$label\positions.yml"
        if ($dataState -eq 'access-denied') { Write-Output "  ${pos}: data directory not readable by $([Security.Principal.WindowsIdentity]::GetCurrent().Name) (SYSTEM/Administrators-only tree after a LocalSystem Apply): run Verify elevated"; continue }
        if (-not (Test-Path -LiteralPath $pos)) { Write-Output "  ${pos}: absent (Alloy not installed or not started yet; data dir: $dataState)"; continue }
        $pi = Get-Item -LiteralPath $pos -Force
        try { $entries = Read-Positions ([System.IO.File]::ReadAllText($pos)) } catch { Write-Output "  ${pos}: not readable ($($_.Exception.GetType().Name)); under a LocalSystem install only administrators can read it"; continue }
        $offset = $null
        foreach ($k in $entries.Keys) { if ($k -ieq $logFile -or $k.Replace('/', '\') -ieq $logFile) { $offset = [long]$entries[$k] } }
        Write-Output ("  {0}: modified {1}Z, offset for pfirewall.log = {2}, current pfirewall.log size = {3}" -f $pos, $pi.LastWriteTimeUtc.ToString('s'), $(if ($null -ne $offset) { $offset } else { 'absent' }), $(if ($null -ne $logSize) { $logSize } else { 'n/a' }))
        if ($null -eq $offset -or $null -eq $logSize) { continue }
        if ($rotationMarker) {
            $afterRotation = $pi.LastWriteTimeUtc -gt $rotationMarker
            if ($afterRotation -and $offset -gt 0 -and $offset -le $logSize) { $verdictAdvanced = $true; Write-Output '  verdict: ADVANCED since the last rotation (positions written after the marker; 0 < offset <= size)' }
            elseif ($offset -gt $logSize) { $verdictAdvanced = $false; Write-Output '  verdict: NOT ADVANCED - offset exceeds the current file size (stale pre-rotation offset; the new file has not been read)' }
            elseif (-not $afterRotation) { $verdictAdvanced = $false; Write-Output '  verdict: NOT ADVANCED - positions.yml older than the rotation marker' }
            else { $verdictAdvanced = $false; Write-Output '  verdict: NOT ADVANCED - offset is 0 after the rotation' }
        } else { Write-Output '  verdict: no rotation marker; compare offset with size on a later run' }
    }
    Write-Output '--- reading ---'
    # When did Apply last run? (its transcript and icacls backup live under $backupDir; readable by Users unless a LocalSystem install locked the tree)
    $applyAt = $null
    $backupState = Get-DirState $backupDir
    if ($backupState -eq 'readable') {
        $last = Get-ChildItem -LiteralPath $backupDir -Filter 'pfirewall-acl-before-*.txt' -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc | Select-Object -Last 1
        if ($last) { $applyAt = $last.LastWriteTimeUtc }
    }
    if ($applyAt) { Write-Output "  Last pfirewall-acl.ps1 Apply (icacls backup time): $($applyAt.ToString('s'))Z" }
    elseif ($backupState -eq 'access-denied') { Write-Output "  Apply history under $backupDir not readable by this account (SYSTEM/Administrators-only tree after a LocalSystem Apply): run Verify elevated" }
    else { Write-Output "  Last pfirewall-acl.ps1 Apply: none recorded under $backupDir ($backupState)" }
    $alloyRead = if ($sids['Alloy'] -and (Test-Path -LiteralPath $logFile)) { Test-SidRead $logFile $sids['Alloy'] } else { $null }
    if ($alloyRead -eq $true) { Write-Output '  Alloy SID holds read on pfirewall.log: the predicted loss has NOT occurred (yet). Keep the virtual account; re-run Verify after the next rotation.' }
    elseif ($alloyRead -eq $false) {
        if ($backupState -eq 'access-denied') { Write-Output '  Alloy SID has NO read ACE on pfirewall.log, but the Apply history is unreadable from this account: no conclusion here; run Verify elevated.' }
        elseif (-not $applyAt) { Write-Output '  Alloy SID has NO read ACE on pfirewall.log and no Apply is recorded: this is the pre-Apply baseline, NOT evidence of a lost grant. Nothing to conclude.' }
        elseif (-not $rotationMarker -or $rotationMarker -le $applyAt) { Write-Output '  Alloy SID has NO read ACE on pfirewall.log although Apply ran and no rotation followed it: unexpected (Apply skipped the file, or the ACE was removed by something else). Inspect the Apply transcript; not rotation evidence.' }
        else {
            Write-Output "  Alloy SID has NO read ACE on pfirewall.log and the file was rotated ($($rotationMarker.ToString('s'))Z) AFTER Apply ($($applyAt.ToString('s'))Z): the predicted loss is now OBSERVED."
            if ($verdictAdvanced -eq $false) { Write-Output '  With the positions verdict NOT ADVANCED this transcript is the -Evidence for install-alloy.ps1 -RuntimeAccount LocalSystem.' }
            elseif ($verdictAdvanced -eq $true) { Write-Output '  NOTE: positions still advanced - Alloy kept its open handle across the rotation (FILE_SHARE_DELETE reopen) or runs as SYSTEM; the loss would show on the next Alloy restart. Not yet -Evidence.' }
            else { Write-Output '  Positions verdict unavailable (Alloy not running or positions unreadable): the access loss alone is not yet -Evidence; capture the verdict with Alloy running.' }
        }
    } else { Write-Output '  Alloy SID read on pfirewall.log: could not be determined (ACL unreadable).' }
    Write-Output '  No change made.'
}

function Invoke-Native {
    param([string]$File, [string[]]$Arguments)
    Write-Output ("> {0} {1}" -f $File, ($Arguments -join ' '))
    # PowerShell 5.1 turns redirected stderr into a terminating error under Stop; rely on the exit code instead.
    $ErrorActionPreference = 'Continue'
    & $File @Arguments 2>&1 | ForEach-Object { Write-Output "  $_" }
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0) { throw "$File exited with $LASTEXITCODE" }
}

if ($Mode -eq 'Verify') { Show-Verify; exit 0 }
if ($Mode -eq 'Preflight') {
    Write-Output "=== pfirewall-acl.ps1 Preflight ($(Get-Date -Format s)) ==="
    Write-Output "Elevated: $isAdmin"
    foreach ($s in $services) {
        $svc = Get-Service -Name $s -ErrorAction SilentlyContinue
        $present = if ($svc) { "present ($($svc.Status))" } else { 'absent' }
        try { $sid = Get-ServiceSid $s } catch { $sid = 'n/a' }
        Write-Output "Service ${s}: $present; virtual account NT SERVICE\$s SID $sid"
    }
    Write-Output '--- firewall logging profiles ---'
    try { Get-NetFirewallProfile | ForEach-Object { Write-Output ("  {0}: Enabled={1} LogBlocked={2} LogAllowed={3} LogMaxSizeKilobytes={4} LogFileName={5}" -f $_.Name, $_.Enabled, $_.LogBlocked, $_.LogAllowed, $_.LogMaxSizeKilobytes, $_.LogFileName) } }
    catch { Write-Output "  Get-NetFirewallProfile failed: $($_.Exception.Message)" }
    Write-Output '--- current ACLs ---'
    Show-Acl $logDir
    foreach ($f in $logFiles) { Show-Acl $f }
    Write-Output '  Observed: protected DACL on the files (mpssvc). Predicted, not yet observed: the file grant Apply adds vanishes at'
    Write-Output '  the next rotation. Settle it with -Mode Verify after the first rotation that follows Apply (Codex C3).'
    Write-Output '--- Apply would ---'
    Write-Output "  1. icacls `"$logDir`" /save <backup> /T /C  (into $backupDir)"
    Write-Output "  2. icacls `"$logDir`" /grant *<Alloy SID>:(OI)(CI)R *<telegraf SID>:(OI)(CI)R"
    Write-Output "  3. icacls <each existing log file> /grant *<SID>:R for both SIDs"
    Write-Output '  Rollback would: icacls <parent> /restore <latest backup>, else /remove:g both SIDs.'
    exit 0
}
if (-not $isAdmin) { throw 'Run Apply/Rollback in an administrator PowerShell (Preflight and Verify are the non-elevated modes).' }
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Start-Transcript -Path (Join-Path $backupDir "pfirewall-acl-$Mode-$stamp.log") | Out-Null
try {
    $sids = @{}
    foreach ($s in $services) { $sids[$s] = Get-ServiceSid $s; Write-Output "NT SERVICE\$s = $($sids[$s])" }
    if ($Mode -eq 'Rollback') {
        $backup = Get-ChildItem -LiteralPath $backupDir -Filter 'pfirewall-acl-before-*.txt' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
        if ($backup) {
            # /save was run on $logDir with /T, so entries are relative to its parent.
            Invoke-Native 'icacls.exe' @((Split-Path $logDir -Parent), '/restore', $backup.FullName, '/C')
            Write-Output "Rollback complete: ACLs restored from $($backup.FullName)."
        } else {
            foreach ($p in @($logDir) + ($logFiles | Where-Object { Test-Path -LiteralPath $_ })) {
                foreach ($s in $services) { Invoke-Native 'icacls.exe' @($p, '/remove:g', "*$($sids[$s])", '/C') }
            }
            Write-Output 'Rollback complete: no backup found, the two service SIDs were removed from the directory and log files.'
        }
    } else {
        $backupFile = Join-Path $backupDir "pfirewall-acl-before-$stamp.txt"
        Invoke-Native 'icacls.exe' @($logDir, '/save', $backupFile, '/T', '/C')
        if (-not (Test-Path -LiteralPath $backupFile) -or (Get-Item -LiteralPath $backupFile).Length -eq 0) { throw 'ACL backup failed; no change applied.' }
        $present = @($services | Where-Object { Get-Service -Name $_ -ErrorAction SilentlyContinue })
        $absent = @($services | Where-Object { $present -notcontains $_ })
        foreach ($s in $absent) { Write-Warning "Service $s is not registered yet: icacls cannot map its SID (1332). Skipped; re-run  pfirewall-acl.ps1 -Mode Apply  after its installer (add-only, idempotent)." }
        if (-not $present) { throw 'neither service is registered; nothing to grant' }
        $dirGrants = @()
        foreach ($s in $present) { $dirGrants += "*$($sids[$s]):(OI)(CI)R" }
        Invoke-Native 'icacls.exe' @(@($logDir, '/grant') + $dirGrants)
        foreach ($f in $logFiles) {
            if (-not (Test-Path -LiteralPath $f)) { Write-Output "  $f absent, skipped"; continue }
            $fileGrants = @()
            foreach ($s in $present) { $fileGrants += "*$($sids[$s]):R" }
            Invoke-Native 'icacls.exe' @(@($f, '/grant') + $fileGrants)
        }
        Write-Output '--- resulting ACLs (inherited ACEs carry (I)) ---'
        Invoke-Native 'icacls.exe' @($logDir)
        foreach ($f in $logFiles) { if (Test-Path -LiteralPath $f) { Invoke-Native 'icacls.exe' @($f) } }
        Write-Output "Applied. Backup: $backupFile. The file grants are expected (not yet observed) to be dropped by mpssvc at the next rotation: after it, run  pfirewall-acl.ps1 -Mode Verify  (read-only) and keep that transcript; it decides whether the virtual account stays (grant survived or Alloy still advances) or the LocalSystem fallback is in scope."
    }
} finally { Stop-Transcript | Out-Null }
