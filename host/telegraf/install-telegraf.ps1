#Requires -Version 5.1
<#
.SYNOPSIS
Attended installer for the native Telegraf host collector on the Ryzen
(household observability M3 pilot, 2026-09-16).

.DESCRIPTION
  -Mode Preflight   Non-elevated, read-only, no secrets: prints what exists, validates the
                    manifest with the evaluator, runs every exec script once (temp state
                    dir) and lists what Apply would do. Executed now as the CONTRACT.md
                    preflight record. Never reads or lists iot-backend\secrets or
                    ~\.grafana-recovery-keys.
  -Mode Apply       Attended, elevated. Downloads telegraf-1.40.0_windows_amd64.zip
                    (SHA256 pinned below, Get-FileHash must match or it aborts), installs
                    C:\Program Files\telegraf\telegraf.exe, config to C:\ProgramData\telegraf,
                    registers the service, switches it to the virtual account
                    NT SERVICE\telegraf, sets ACLs (token fragment ACL BEFORE its content),
                    writes the token fragment from -TokenFile (never printed), runs one
                    --test, starts the service and checks its log.
  -Mode Rollback    Attended, elevated. Stops and removes the service, the ACL grants,
                    C:\ProgramData\telegraf (including the token fragment) and
                    C:\Program Files\telegraf.

.PARAMETER TokenFile
JSON written by iot-backend\tools\provision_household.py --apply for token
"telegraf-ryzen" (key "token"), default
C:\Users\david\Repos\iot-backend\secrets\household-telegraf-ryzen-token.json. Read only
by Apply, in memory, never echoed.
.PARAMETER GrantEventLogReaders
Apply only, default off: also add NT SERVICE\telegraf to "Event Log Readers" so
source-progress.ps1 can read the Security channel's newest RecordId. A separate
grant decision (architecture 7); without it winsec progress stays unknown.
.PARAMETER SkipExec
Preflight only: do not run the exec scripts.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File install-telegraf.ps1 -Mode Preflight
# elevated PowerShell:
powershell -NoProfile -ExecutionPolicy Bypass -File install-telegraf.ps1 -Mode Apply
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('Preflight', 'Apply', 'Rollback')][string]$Mode,
    [string]$TokenFile = 'C:\Users\david\Repos\iot-backend\secrets\household-telegraf-ryzen-token.json',
    [string]$Manifest = 'C:\Users\david\Repos\iot-backend\config\monitoring\dependencies.json',
    [switch]$GrantEventLogReaders,
    [switch]$SkipExec
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

# ----------------------------------------------------------------------------- constants
$TelegrafVersion = '1.40.0'
$ZipUrl = "https://dl.influxdata.com/telegraf/releases/telegraf-${TelegrafVersion}_windows_amd64.zip"
# SHA256 as listed on https://github.com/influxdata/telegraf/releases/tag/v1.40.0 (read 2026-09-16;
# the .sha256 sidecar URL on dl.influxdata.com returned 404). Apply aborts on mismatch.
$ZipSha256 = '9d85e3fa89d99e4b0e53e4aa40f069e828204cf5548ede9b9b7c95c31fe869dd'
$ProgramDir = 'C:\Program Files\telegraf'
$DataDir = 'C:\ProgramData\telegraf'
$ConfDir = Join-Path $DataDir 'telegraf.d'
$ExecDir = Join-Path $DataDir 'exec'
$MonDir = Join-Path $DataDir 'monitoring'
$StateDir = Join-Path $DataDir 'state'
$LogDir = Join-Path $DataDir 'logs'
$TokenFragment = Join-Path $ConfDir 'influxdb-output.conf'
$ServiceName = 'telegraf'
$ServiceAccount = 'NT SERVICE\telegraf'
$ManifestDir = Split-Path -Parent $Manifest
$AlloyData = 'C:\ProgramData\GrafanaLabs\Alloy\data'
$FirewallLogDir = Join-Path $env:SystemRoot 'System32\LogFiles\Firewall'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcConf = Join-Path $Here 'telegraf.conf'
$SrcExec = Join-Path $Here 'exec'
$SrcEvaluator = Join-Path (Split-Path -Parent $Here) 'monitoring\service_health.ps1'
$SrcFragmentExample = Join-Path $Here 'telegraf.d\influxdb-output.conf.example'

function Say([string]$t) { [Console]::Out.WriteLine($t) }
function Fact([string]$k, [string]$v) { Say ('  {0,-46} {1}' -f $k, $v) }
function Test-Admin { return ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }
function Exists([string]$p) { try { if (Test-Path -LiteralPath $p -ErrorAction Stop) { 'present' } else { 'absent' } } catch [System.UnauthorizedAccessException] { 'present (protected: no read for this user)' } catch { 'absent' } }
function ServiceFact([string]$n) { $s = Get-Service -Name $n -ErrorAction SilentlyContinue; if ($s) { "$($s.Status) / $($s.StartType)" } else { 'not installed' } }
function AclHas([string]$path, [string]$identity) {
    try { return [bool](@((Get-Acl -LiteralPath $path).Access | Where-Object { $_.IdentityReference.Value -eq $identity }).Count) } catch { return $false }
}
function GroupHas([string]$group, [string]$member) {
    try { return [bool](@(Get-LocalGroupMember -Group $group -ErrorAction Stop | Where-Object { $_.Name -eq $member -or $_.Name -like "*\$($member.Split('\')[-1])" }).Count) } catch { return $false }
}
function Invoke-Native([string]$exe, [string[]]$arguments) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe; $psi.Arguments = ($arguments -join ' '); $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true; $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
    $p = [System.Diagnostics.Process]::Start($psi); $out = $p.StandardOutput.ReadToEnd(); $err = $p.StandardError.ReadToEnd(); $p.WaitForExit()
    return @{ exit = $p.ExitCode; out = $out; err = $err }
}
function Assert-Native([string]$exe, [string[]]$arguments) {
    $r = Invoke-Native $exe $arguments
    if ($r.exit -ne 0) { throw "$exe $($arguments -join ' ') failed ($($r.exit)): $($r.out) $($r.err)" }
    return $r
}
function Read-Token([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { throw "token file not found: $path (create it with iot-backend\tools\provision_household.py --apply)" }
    $raw = [System.IO.File]::ReadAllText($path)
    $token = if ($raw.TrimStart().StartsWith('{')) { (ConvertFrom-Json $raw).token } else { ($raw -split "`r?`n")[0] }
    if (-not $token -or $token -notmatch '^[A-Za-z0-9+/=_-]+$') { throw 'token file is empty or contains characters outside [A-Za-z0-9+/=_-]' }
    return [string]$token
}

# ----------------------------------------------------------------------------- preflight
function Invoke-Preflight {
    Say "== ryzen telegraf preflight (read-only) $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')) as $env:USERNAME on $env:COMPUTERNAME elevated=$(Test-Admin)"
    Say '-- host'
    Fact 'powershell' $PSVersionTable.PSVersion.ToString()
    Fact 'os' ((Get-CimInstance Win32_OperatingSystem).Caption + ' ' + (Get-CimInstance Win32_OperatingSystem).Version)
    Fact 'docker engine (docker version)' $(try { (& docker version --format '{{.Server.Version}}' 2>$null) } catch { 'not answering' })
    Say '-- services'
    foreach ($n in @('telegraf', 'Alloy', 'com.docker.service', 'W32Time')) { Fact "service $n" (ServiceFact $n) }
    Say '-- paths'
    Fact "$ProgramDir\telegraf.exe" (Exists "$ProgramDir\telegraf.exe")
    foreach ($p in @("$DataDir\telegraf.conf", $TokenFragment, $ExecDir, $MonDir, $StateDir, $LogDir, $AlloyData, "$AlloyData\loki.source.file.*", "$AlloyData\loki.source.windowsevent.*")) { Fact $p (Exists $p) }
    Fact 'pfirewall.log' $(try { $i = Get-Item -LiteralPath (Join-Path $FirewallLogDir 'pfirewall.log') -Force; "present, $($i.Length) bytes, mtime $($i.LastWriteTimeUtc.ToString('u'))" } catch { 'absent or not listable' })
    Say '-- identity grants (NT SERVICE\telegraf resolves only once the service exists)'
    Fact 'firewall log dir ACL has NT SERVICE\telegraf' (AclHas $FirewallLogDir $ServiceAccount)
    Fact 'manifest dir ACL has NT SERVICE\telegraf' (AclHas $ManifestDir $ServiceAccount)
    Fact 'Alloy data ACL has NT SERVICE\telegraf' $(if (Test-Path -LiteralPath $AlloyData) { AclHas $AlloyData $ServiceAccount } else { 'n/a (absent)' })
    Fact 'Event Log Readers has NT SERVICE\telegraf' (GroupHas 'Event Log Readers' $ServiceAccount)
    Fact 'Performance Monitor Users has NT SERVICE\telegraf (win_perf_counters needs it)' (GroupHas 'Performance Monitor Users' $ServiceAccount)
    Fact 'docker-users has NT SERVICE\telegraf' "$(GroupHas 'docker-users' $ServiceAccount) (must stay false: D11)"
    Say '-- sources'
    foreach ($p in @($SrcConf, $SrcEvaluator, $SrcFragmentExample, "$SrcExec\lp.ps1", "$SrcExec\service-health.ps1", "$SrcExec\logging-state.ps1", "$SrcExec\source-progress.ps1", "$SrcExec\host-session.ps1", "$SrcExec\clock-offset.ps1", $Manifest)) {
        $crlf = if ((Test-Path -LiteralPath $p) -and ([System.IO.File]::ReadAllText($p).Contains("`r"))) { ' (CRLF!)' } else { '' }
        Fact $p ((Exists $p) + $crlf)
    }
    Fact 'manifest validation' $(try { (& $SrcEvaluator -Command validate -ManifestPath $Manifest 2>&1 | Out-String).Trim() } catch { 'FAILED: ' + $_.Exception.Message })
    Say '-- download'
    Fact 'url' $ZipUrl
    Fact 'expected sha256' $ZipSha256
    $zip = Join-Path $env:TEMP "telegraf-${TelegrafVersion}_windows_amd64.zip"
    Fact "cached $zip" $(if (Test-Path -LiteralPath $zip) { 'present, sha256 ' + $(if ((Get-FileHash -Algorithm SHA256 $zip).Hash.ToLowerInvariant() -eq $ZipSha256) { 'matches' } else { 'DIFFERS' }) } else { 'absent (downloaded by Apply)' })
    Fact 'token file' 'presence not checked (contract: never read or list iot-backend\secrets or ~\.grafana-recovery-keys)'
    if (-not $SkipExec) {
        Say '-- exec scripts, run once now as this user (read-only; state in a temp dir)'
        $tmpState = Join-Path $env:TEMP ('telegraf-preflight-' + [guid]::NewGuid().ToString('n'))
        foreach ($s in @('logging-state', 'clock-offset', 'host-session', 'source-progress', 'service-health')) {
            $args = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', "`"$SrcExec\$s.ps1`"")
            if ($s -eq 'source-progress') { $args += @('-StateDir', "`"$tmpState`"") }
            $r = Invoke-Native 'powershell.exe' $args
            $lines = @($r.out -split "`n" | Where-Object { $_.Trim() })
            $run = $lines | Where-Object { $_ -like 'exec_run,*' } | Select-Object -Last 1
            Fact "$s.ps1" ("exit $($r.exit), $($lines.Count) lines; " + $(if ($run) { $run -replace ' \d{19}$', '' } else { 'no exec_run row' }))
        }
        if (Test-Path -LiteralPath $tmpState) { Remove-Item -LiteralPath $tmpState -Recurse -Force -ErrorAction SilentlyContinue }
    }
    Say '-- Apply would'
    Say "  1 download $ZipUrl to `$env:TEMP, verify sha256 == $ZipSha256 (abort on mismatch), extract telegraf.exe to $ProgramDir"
    Say "  2 create $DataDir\{telegraf.d,exec,monitoring,state,logs}; copy telegraf.conf, exec\*.ps1, monitoring\service_health.ps1"
    Say "  3 telegraf.exe --config $DataDir\telegraf.conf --config-directory $ConfDir service install; sc.exe sidtype telegraf unrestricted; sc.exe config telegraf obj= `"$ServiceAccount`"; add $ServiceAccount to Performance Monitor Users (perf-counter read)"
    Say "  4 ACLs: $DataDir (directory) inheritance off, SYSTEM/Administrators F, $ServiceAccount RX; every existing child /reset so it inherits (files never get (OI)(CI) ACEs); state, logs: $ServiceAccount M; $TokenFragment inheritance off, SYSTEM/Administrators F, $ServiceAccount R, THEN write the token stanza from $TokenFile"
    Say "  5 grant $ServiceAccount (OI)(CI)R on $ManifestDir and on $AlloyData (if present; log-collector territory, read only)$(if ($GrantEventLogReaders) { '; add to Event Log Readers' } else { '; Event Log Readers NOT granted (-GrantEventLogReaders)' })"
    Say "  6 telegraf.exe --test --input-filter win_services:exec; Start-Service telegraf; check $LogDir\telegraf.log for E! lines"
    Say '  no writes were made by this preflight'
}

# ----------------------------------------------------------------------------- apply
function Invoke-Apply {
    if (-not (Test-Admin)) { throw 'Apply needs an elevated PowerShell (run as Administrator)' }
    foreach ($p in @($SrcConf, $SrcEvaluator, $SrcFragmentExample, "$SrcExec\lp.ps1")) { if (-not (Test-Path -LiteralPath $p)) { throw "source missing: $p" } }
    $token = Read-Token $TokenFile
    & $SrcEvaluator -Command validate -ManifestPath $Manifest | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "manifest validation failed for $Manifest (see service_health.ps1 -Command validate)" }
    Say "== apply $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))"

    Say '-- 1 download and verify'
    $zip = Join-Path $env:TEMP "telegraf-${TelegrafVersion}_windows_amd64.zip"
    if (-not (Test-Path -LiteralPath $zip) -or (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLowerInvariant() -ne $ZipSha256) {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $ZipUrl -OutFile $zip -UseBasicParsing
    }
    $hash = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLowerInvariant()
    if ($hash -ne $ZipSha256) { Remove-Item -LiteralPath $zip -Force; throw "sha256 mismatch for $zip : got $hash, expected $ZipSha256 (download removed)" }
    Say "  sha256 ok: $hash"
    $extract = Join-Path $env:TEMP "telegraf-${TelegrafVersion}-extract"
    if (Test-Path -LiteralPath $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $exe = Get-ChildItem -Path $extract -Recurse -Filter 'telegraf.exe' | Select-Object -First 1
    if (-not $exe) { throw 'telegraf.exe not found in the archive' }
    New-Item -ItemType Directory -Path $ProgramDir -Force | Out-Null
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -ne 'Stopped') { Stop-Service -Name $ServiceName -Force }
    Copy-Item -LiteralPath $exe.FullName -Destination (Join-Path $ProgramDir 'telegraf.exe') -Force
    Say "  installed $ProgramDir\telegraf.exe ($((& (Join-Path $ProgramDir 'telegraf.exe') version) -join ' '))"

    Say '-- 2 configuration'
    foreach ($d in @($DataDir, $ConfDir, $ExecDir, $MonDir, $StateDir, $LogDir)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    # Repair pass BEFORE any file is touched (2026-09-17: a previous run of this script left
    # every file under $DataDir with an empty DACL, so even an elevated Copy-Item was denied).
    # Administrators own those files, so /reset works; the service ACE is added in step 4
    # (the service may not be registered yet here, and icacls cannot map its SID before that).
    Assert-Native 'icacls.exe' @("`"$DataDir`"", '/inheritance:r', '/grant:r', '"NT AUTHORITY\SYSTEM:(OI)(CI)F"', '"BUILTIN\Administrators:(OI)(CI)F"', '/Q') | Out-Null
    foreach ($child in Get-ChildItem -LiteralPath $DataDir -Force) { Assert-Native 'icacls.exe' @("`"$($child.FullName)`"", '/reset', '/T', '/C', '/Q') | Out-Null }
    Say "  $DataDir DACL: SYSTEM/Administrators F (protected), children inherit; the service read grant follows in step 4"
    Copy-Item -LiteralPath $SrcConf -Destination (Join-Path $DataDir 'telegraf.conf') -Force
    Get-ChildItem -Path $SrcExec -Filter '*.ps1' | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $ExecDir $_.Name) -Force }
    Copy-Item -LiteralPath $SrcEvaluator -Destination (Join-Path $MonDir 'service_health.ps1') -Force

    Say '-- 3 service registration and virtual account'
    $telegrafExe = Join-Path $ProgramDir 'telegraf.exe'
    if (-not (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)) {
        Assert-Native $telegrafExe @('--config', "`"$DataDir\telegraf.conf`"", '--config-directory', "`"$ConfDir`"", 'service', 'install') | Out-Null
    }
    Assert-Native 'sc.exe' @('sidtype', $ServiceName, 'unrestricted') | Out-Null
    Assert-Native 'sc.exe' @('config', $ServiceName, 'obj=', "`"$ServiceAccount`"") | Out-Null
    Assert-Native 'sc.exe' @('config', $ServiceName, 'start=', 'delayed-auto') | Out-Null
    Say "  service $ServiceName runs as $ServiceAccount (delayed-auto)"
    # Performance counters (HKLM\...\Perflib) are readable by INTERACTIVE, SYSTEM, LOCAL/NETWORK
    # SERVICE, Administrators and the Performance Monitor/Log Users groups only; a virtual
    # service account is none of these, so inputs.win_perf_counters returned "No data to
    # return" for ever on the first live install (2026-09-17). Performance Monitor Users is the
    # least-privilege read grant (no log-collection, no configuration rights).
    if (-not (GroupHas 'Performance Monitor Users' $ServiceAccount)) { Add-LocalGroupMember -Group 'Performance Monitor Users' -Member $ServiceAccount; Say "  Performance Monitor Users: $ServiceAccount added (takes effect at the service start below)" }
    else { Say "  Performance Monitor Users: $ServiceAccount already a member" }

    Say '-- 4 ACLs (fragment ACL before its content)'
    # Protected DACL on the directory only, then reset every existing child so it INHERITS it.
    # (2026-09-17 live finding: `/inheritance:r /grant:r ...(OI)(CI)... /T` also processes the
    # files, and (OI)(CI) ACEs do not apply to files, so every file ended with an EMPTY DACL:
    # "open telegraf.conf: Access is denied" for the service and for the elevated operator.)
    Assert-Native 'icacls.exe' @("`"$DataDir`"", '/inheritance:r', '/grant:r', '"NT AUTHORITY\SYSTEM:(OI)(CI)F"', '"BUILTIN\Administrators:(OI)(CI)F"', "`"${ServiceAccount}:(OI)(CI)RX`"", '/Q') | Out-Null
    foreach ($child in Get-ChildItem -LiteralPath $DataDir -Force) { Assert-Native 'icacls.exe' @("`"$($child.FullName)`"", '/reset', '/T', '/C', '/Q') | Out-Null }
    foreach ($d in @($StateDir, $LogDir)) { Assert-Native 'icacls.exe' @("`"$d`"", '/grant', "`"${ServiceAccount}:(OI)(CI)M`"", '/Q') | Out-Null }
    if (-not (Test-Path -LiteralPath $TokenFragment)) { New-Item -ItemType File -Path $TokenFragment -Force | Out-Null }
    Assert-Native 'icacls.exe' @("`"$TokenFragment`"", '/inheritance:r', '/grant:r', '"NT AUTHORITY\SYSTEM:F"', '"BUILTIN\Administrators:F"', "`"${ServiceAccount}:R`"", '/Q') | Out-Null
    $stanza = [System.IO.File]::ReadAllText($SrcFragmentExample) -replace 'REPLACED-BY-install-telegraf\.ps1', $token
    [System.IO.File]::WriteAllText($TokenFragment, $stanza, (New-Object System.Text.UTF8Encoding($false)))
    $token = $null; $stanza = $null
    Say "  wrote $TokenFragment (token not shown)"

    Say '-- 5 read grants for the collector identity'
    Assert-Native 'icacls.exe' @("`"$ManifestDir`"", '/grant', "`"${ServiceAccount}:(OI)(CI)R`"", '/Q') | Out-Null
    Say "  $ManifestDir : $ServiceAccount (OI)(CI)R"
    if (Test-Path -LiteralPath $AlloyData) {
        Assert-Native 'icacls.exe' @("`"$AlloyData`"", '/grant', "`"${ServiceAccount}:(OI)(CI)R`"", '/Q') | Out-Null
        Say "  $AlloyData : $ServiceAccount (OI)(CI)R (log-collector territory: read grant only)"
    }
    else { Say "  $AlloyData absent: source_progress stays unknown until Alloy is installed and this grant is re-run" }
    if ($GrantEventLogReaders) {
        if (-not (GroupHas 'Event Log Readers' $ServiceAccount)) { Add-LocalGroupMember -Group 'Event Log Readers' -Member $ServiceAccount }
        Say "  Event Log Readers: $ServiceAccount added (needs a service restart to take effect)"
    }
    else { Say '  Event Log Readers: not granted (winsec source_progress stays unknown); re-run with -GrantEventLogReaders to add' }

    Say '-- 6 test run and start'
    $t = Invoke-Native $telegrafExe @('--config', "`"$DataDir\telegraf.conf`"", '--config-directory', "`"$ConfDir`"", '--test', '--input-filter', 'win_services:exec')
    $testLines = @($t.out -split "`n" | Where-Object { $_ -match '^(service_health|win_services|logging_state|source_progress|host_session|clock_offset|exec_run)' })
    Say "  --test (as $env:USERNAME, not the service account): exit $($t.exit), $($testLines.Count) metric lines"
    if ($t.exit -ne 0) { Say ('  ' + (($t.err -split "`n" | Select-Object -First 5) -join "`n  ")) }
    Start-Service -Name $ServiceName
    Start-Sleep -Seconds 90
    $s = Get-Service -Name $ServiceName
    Say "  service status: $($s.Status)"
    $log = Join-Path $LogDir 'telegraf.log'
    if (Test-Path -LiteralPath $log) {
        $errs = @(Get-Content -LiteralPath $log -Tail 200 | Where-Object { $_ -match ' E! ' })
        Say "  E! lines in the log tail: $($errs.Count) (a prometheus/Alloy connection error is expected until Alloy is installed)"
        $errs | Select-Object -First 8 | ForEach-Object { Say "    $_" }
    }
    Say "done. Verify in Influx: from(bucket:\"infra\") |> range(start:-10m) |> filter(fn:(r)=> r.host==\"ryzen\"). Rollback: -Mode Rollback"
}

# ----------------------------------------------------------------------------- rollback
function Invoke-Rollback {
    if (-not (Test-Admin)) { throw 'Rollback needs an elevated PowerShell (run as Administrator)' }
    Say "== rollback $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        if ($svc.Status -ne 'Stopped') { Stop-Service -Name $ServiceName -Force }
        # Remove grants while the virtual account SID still resolves.
        foreach ($p in @($ManifestDir, $AlloyData)) { if (Test-Path -LiteralPath $p) { Invoke-Native 'icacls.exe' @("`"$p`"", '/remove:g', "`"$ServiceAccount`"", '/Q') | Out-Null } }
        if (GroupHas 'Event Log Readers' $ServiceAccount) { Remove-LocalGroupMember -Group 'Event Log Readers' -Member $ServiceAccount -ErrorAction SilentlyContinue }
        if (GroupHas 'Performance Monitor Users' $ServiceAccount) { Remove-LocalGroupMember -Group 'Performance Monitor Users' -Member $ServiceAccount -ErrorAction SilentlyContinue }
        $exe = Join-Path $ProgramDir 'telegraf.exe'
        if (Test-Path -LiteralPath $exe) { Invoke-Native $exe @('service', 'uninstall') | Out-Null } else { Invoke-Native 'sc.exe' @('delete', $ServiceName) | Out-Null }
        Say '  service removed'
    }
    foreach ($d in @($DataDir, $ProgramDir)) { if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d -Recurse -Force; Say "  removed $d" } }
    Say 'done (Influx token telegraf-ryzen itself is not revoked here)'
}

switch ($Mode) {
    'Preflight' { Invoke-Preflight }
    'Apply' { Invoke-Apply }
    'Rollback' { Invoke-Rollback }
}
