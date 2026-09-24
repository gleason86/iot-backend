#Requires -Version 5.1
<#
source_progress for Telegraf on the Ryzen (runs as NT SERVICE\telegraf every 60 s).
Architecture 3.5 four states: advancing | caught-up idle | stalled | unknown.

Sources:
  winfw      Alloy loki.source.file positions.yml (complex-key YAML, entry whose
             path is pfirewall.log) offset vs the file's current Length.
             The reading is trusted only when this account can actually OPEN
             the log for read: Get-Item's Length comes from the directory entry
             (Users can list the directory) and is lazily updated while mpssvc
             holds the file open, so without a read handle the comparison is
             not evidence of progress. If the open is denied the row is
             state="unknown" with reason
             "log-unreadable (<identity> lacks read; pfirewall-acl.ps1 or the
             protected DACL)" where <identity> is the running account
             (NT SERVICE\telegraf under the service). Codex C3 (2026-09-16):
             moving Alloy to LocalSystem does not give this account read on
             the log, so unknown progress must stay visible, never absent.
  win*       Alloy loki.source.windowsevent bookmark.xml (<Bookmark Channel='..'
             RecordId='..'/>) vs the newest RecordId from
             Get-WinEvent -LogName <channel> -MaxEvents 1. Security needs
             Event Log Readers: without that membership the newest RecordId is
             unreadable (UnauthorizedAccessException) -> its own row,
             state="unknown", reason "channel-unreadable (<identity> not in
             Event Log Readers; install-telegraf.ps1 -GrantEventLogReaders)".
             Channel -> source tag: Security=winsec, System=winsys,
             TerminalServices-LocalSessionManager=winlsm,
             TerminalServices-RemoteConnectionManager=winrcm,
             RemoteDesktopServices-RdpCoreTS=winrdpcore, Windows Firewall With
             Advanced Security/Firewall=winfwpolicy.
Every source emits exactly one row per run, whatever fails: an unexpected
exception inside a source block still produces state="unknown",
reason="exception:<type>" for that source (never a silently absent row).
Stall detection needs memory: -StateDir\source-progress.json (offset, when it last
moved). Fields: state, offset (int), size (int), newest_record (string), checked_at
(string), reason (string, additive). Alloy absent -> unknown, reason
alloy_positions_absent / bookmark_absent.
#>
[CmdletBinding()]
param(
    [string]$AlloyData = 'C:\ProgramData\GrafanaLabs\Alloy\data',
    [string]$StateDir = (Join-Path $env:ProgramData 'telegraf\state'),
    [string]$FirewallLog = (Join-Path $env:SystemRoot 'System32\LogFiles\Firewall\pfirewall.log'),
    [int]$StallSeconds = 300
)
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'lp.ps1')

$ts = Get-NowNs
$now = [double]$ts / 1e9
$checkedAt = [DateTimeOffset]::FromUnixTimeMilliseconds([long]($ts / 1000000)).ToString('yyyy-MM-ddTHH:mm:ssZ')
$identity = try { [Security.Principal.WindowsIdentity]::GetCurrent().Name } catch { 'NT SERVICE\telegraf' }
$channels = [ordered]@{
    'Security' = 'winsec'
    'System' = 'winsys'
    'Microsoft-Windows-TerminalServices-LocalSessionManager/Operational' = 'winlsm'
    'Microsoft-Windows-TerminalServices-RemoteConnectionManager/Operational' = 'winrcm'
    'Microsoft-Windows-RemoteDesktopServices-RdpCoreTS/Operational' = 'winrdpcore'
    'Microsoft-Windows-Windows Firewall With Advanced Security/Firewall' = 'winfwpolicy'
}

function Read-Positions([string]$text) {
    # go-yaml complex-key layout: "? path: X" / "labels: Y" / ": value"; tolerant.
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

function Test-LogReadable([string]$path) {
    # A real read handle (sharing write+delete with mpssvc, which holds the file
    # open and renames it at rotation). Returns '' when readable, else the reason.
    try {
        $fs = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete))
        $fs.Close()
        return ''
    } catch [System.UnauthorizedAccessException] {
        return "log-unreadable ($identity lacks read; pfirewall-acl.ps1 or the protected DACL)"
    } catch [System.IO.FileNotFoundException] {
        return 'log_absent'
    } catch [System.IO.DirectoryNotFoundException] {
        return 'log_absent'
    } catch {
        return 'log_open_failed:' + $_.Exception.GetType().Name
    }
}

function Get-Progress($prev, $offset, $size, [double]$now, [int]$stall) {
    if ($null -eq $offset -or $null -eq $size) { return @{ state = 'unknown'; reason = 'no_reading'; entry = $prev } }
    $moved = ($null -eq $prev) -or ([long]$prev.offset -ne [long]$offset)
    $movedAt = if ($moved) { $now } else { [double]$prev.moved_at }
    $entry = @{ offset = [long]$offset; size = [long]$size; moved_at = $movedAt; checked_at = $now }
    if ($moved) { return @{ state = 'advancing'; reason = $(if ($null -eq $prev) { 'first_reading' } else { 'offset_moved' }); entry = $entry } }
    if ([long]$offset -ge [long]$size) { return @{ state = 'caught-up idle'; reason = 'offset_at_size'; entry = $entry } }
    $behind = [int]($now - $movedAt)
    if ($behind -gt $stall) { return @{ state = 'stalled'; reason = "behind_for_${behind}s"; entry = $entry } }
    return @{ state = 'advancing'; reason = "behind_within_tolerance_${behind}s"; entry = $entry }
}
function New-ProgressRow([string]$source, $p, $offset, $size, [string]$newest, [string]$reasonOverride) {
    $f = @('state=' + (ConvertTo-LpString $p.state))
    if ($null -ne $offset) { $f += 'offset=' + [long]$offset + 'i' }
    if ($null -ne $size) { $f += 'size=' + [long]$size + 'i' }
    $f += 'newest_record=' + (ConvertTo-LpString $(if ($newest) { $newest } else { '-' }))
    $f += 'checked_at=' + (ConvertTo-LpString $checkedAt)
    $f += 'reason=' + (ConvertTo-LpString $(if ($reasonOverride) { $reasonOverride } else { $p.reason }))
    return 'source_progress,source=' + (ConvertTo-LpTag $source) + ' ' + ($f -join ',') + ' ' + $ts
}
function New-UnknownRow([string]$source, [string]$reason) {
    return New-ProgressRow $source @{ state = 'unknown'; reason = $reason } $null $null '-' $reason
}

# --- state file
$statePath = Join-Path $StateDir 'source-progress.json'
$state = @{}
try { if (Test-Path -LiteralPath $statePath) { $raw = ConvertFrom-Json ([System.IO.File]::ReadAllText($statePath)); foreach ($p in $raw.PSObject.Properties) { $state[$p.Name] = @{ offset = [long]$p.Value.offset; size = [long]$p.Value.size; moved_at = [double]$p.Value.moved_at; checked_at = [double]$p.Value.checked_at } } } } catch { $state = @{} }

$lines = @(); $rows = 0; $errors = @()

# --- pfirewall.log via loki.source.file positions (one row, always)
try {
    $size = $null; $offset = $null; $reason = ''
    $unreadable = Test-LogReadable $FirewallLog
    try { $size = [long](Get-Item -LiteralPath $FirewallLog -Force -ErrorAction Stop).Length; $newestFw = (Get-Item -LiteralPath $FirewallLog -Force).LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ') } catch { $reason = 'log_unreadable:' + $_.Exception.GetType().Name; $newestFw = '-' }
    $posFiles = @(Get-ChildItem -Path (Join-Path $AlloyData 'loki.source.file.*\positions.yml') -ErrorAction SilentlyContinue)
    if ($posFiles.Count -eq 0) { $reason = $(if ($reason) { $reason + ';' } else { '' }) + 'alloy_positions_absent' }
    else {
        $found = $false
        foreach ($pf in $posFiles) {
            try { $entries = Read-Positions ([System.IO.File]::ReadAllText($pf.FullName)) } catch { $reason = 'positions_unreadable:' + $_.Exception.GetType().Name; continue }
            foreach ($k in $entries.Keys) { if ($k -ieq $FirewallLog -or $k.Replace('/', '\') -ieq $FirewallLog) { $offset = [long]$entries[$k]; $found = $true } }
        }
        if (-not $found -and -not $reason) { $reason = 'positions_entry_missing' }
    }
    if ($unreadable) {
        # Explicit (Codex C3): no read handle on the log -> the reading is not evidence.
        # offset/size stay on the row when known so the dashboard still shows them.
        $reason = $unreadable + $(if ($reason) { ';' + $reason } else { '' })
        $p = @{ state = 'unknown'; reason = $reason; entry = $null }
    } else {
        $p = Get-Progress $state['winfw'] $offset $size $now $StallSeconds
        if ($p.entry) { $state['winfw'] = $p.entry }
    }
    $lines += New-ProgressRow 'winfw' $p $offset $size $newestFw $(if ($p.state -eq 'unknown') { $reason } else { '' })
} catch {
    $lines += New-UnknownRow 'winfw' ('exception:' + $_.Exception.GetType().Name)
}
$rows++

# --- Windows event channels via loki.source.windowsevent bookmarks (one row per channel, always)
$bookmarks = @{}
try {
    foreach ($bf in @(Get-ChildItem -Path (Join-Path $AlloyData 'loki.source.windowsevent.*\*.xml') -ErrorAction SilentlyContinue)) {
        try { $xml = [System.IO.File]::ReadAllText($bf.FullName) } catch { continue }
        foreach ($m in [regex]::Matches($xml, "Channel='([^']+)'\s+RecordId='(\d+)'")) { $bookmarks[$m.Groups[1].Value] = [long]$m.Groups[2].Value }
    }
} catch { $bookmarks = @{} }
foreach ($channel in $channels.Keys) {
    $source = $channels[$channel]
    try {
        $newest = $null; $reason = ''
        try { $ev = Get-WinEvent -LogName $channel -MaxEvents 1 -ErrorAction Stop; $newest = [long]$ev.RecordId }
        catch {
            $t = $_.Exception.GetType().Name
            if ($t -eq 'UnauthorizedAccessException' -or $_.Exception.Message -match 'unauthorized|denied') {
                if ($channel -eq 'Security') { $reason = "channel-unreadable ($identity not in Event Log Readers; install-telegraf.ps1 -GrantEventLogReaders)" }
                else { $reason = 'channel_access_denied:' + $t }
            }
            elseif ($_.Exception.Message -match 'No events were found') { $newest = 0 }
            else { $reason = 'channel_query_failed:' + $t }
        }
        $offset = $null
        if ($bookmarks.ContainsKey($channel)) { $offset = $bookmarks[$channel] } else { $reason = $(if ($reason) { $reason + ';' } else { '' }) + 'bookmark_absent' }
        $p = Get-Progress $state[$source] $offset $newest $now $StallSeconds
        if ($p.entry) { $state[$source] = $p.entry }
        $lines += New-ProgressRow $source $p $offset $newest $(if ($null -ne $newest) { [string]$newest } else { '-' }) $(if ($p.state -eq 'unknown') { $reason } else { '' })
    } catch {
        $lines += New-UnknownRow $source ('exception:' + $_.Exception.GetType().Name)
    }
    $rows++
}

# --- persist state
$saveError = ''
try {
    if (-not (Test-Path -LiteralPath $StateDir)) { New-Item -ItemType Directory -Path $StateDir -Force -ErrorAction Stop | Out-Null }
    $tmp = $statePath + '.tmp'
    [System.IO.File]::WriteAllText($tmp, (ConvertTo-Json $state -Depth 4), $script:Utf8NoBom)
    Move-Item -LiteralPath $tmp -Destination $statePath -Force -ErrorAction Stop
}
catch { $saveError = 'state_not_saved:' + $_.Exception.GetType().Name }
$lines += New-ExecRun 'source-progress' ($saveError -eq '') $rows $saveError $ts
Write-LpLines $lines
exit 0
