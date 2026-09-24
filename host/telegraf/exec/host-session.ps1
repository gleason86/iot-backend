#Requires -Version 5.1
<#
host_session for Telegraf on the Ryzen (runs as NT SERVICE\telegraf every 60 s).

Parses `quser` (fixed-width columns USERNAME SESSIONNAME ID STATE IDLE TIME LOGON
TIME; exit 0, unlike `query session` which exits 1 while still printing). One row
per interactive user session:
  host_session,session_id=<ID> user="david",type="rdp|console|disconnected",
               state="Active|Disc",since="<logon time as printed>",remote="-"
remote stays "-": the RDP client address is not exposed by quser; it comes from the
Loki winrcm/winlsm events (1149/21). Whether quser enumerates sessions under the
virtual service account is verified at apply (exec_run error=quser_exit_N otherwise).
#>
[CmdletBinding()] param()
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'lp.ps1')

$ts = Get-NowNs
$r = Get-NativeOutput 'quser.exe' @()
if ($r.exit -ne 0 -and -not $r.stdout.Trim()) {
    $err = (($r.stdout + ' ' + $r.stderr) -replace '\s+', ' ').Trim()
    Write-LpLines @((New-ExecRun 'host-session' $false 0 ("quser_exit_$($r.exit):" + $err) $ts))
    exit 0
}
$textLines = @($r.stdout -split "`r?`n" | Where-Object { $_.Trim() })
$lines = @(); $rows = 0
if ($textLines.Count -ge 1 -and $textLines[0] -match 'USERNAME') {
    $header = $textLines[0]
    $cols = @('USERNAME', 'SESSIONNAME', 'ID', 'STATE', 'IDLE TIME', 'LOGON TIME')
    $starts = @($cols | ForEach-Object { $header.IndexOf($_) })
    foreach ($row in $textLines[1..($textLines.Count - 1)]) {
        if ($starts[0] -lt 0) { break }
        $padded = $row.PadRight($header.Length + 40)
        $get = { param($i) $s = $starts[$i]; $e = if ($i + 1 -lt $starts.Count) { $starts[$i + 1] } else { $padded.Length }; $padded.Substring($s, [math]::Max(0, $e - $s)).Trim() }
        $user = (& $get 0).TrimStart('>')
        $sessionName = & $get 1; $id = & $get 2; $state = & $get 3; $logon = & $get 5
        if (-not $user -or $id -notmatch '^\d+$') { continue }
        $type = if ($sessionName -match '^rdp') { 'rdp' } elseif ($sessionName -eq 'console') { 'console' } elseif (-not $sessionName) { 'disconnected' } else { $sessionName }
        $lines += ('host_session,session_id=' + $id + ' user=' + (ConvertTo-LpString $user) + ',type=' + (ConvertTo-LpString $type) +
            ',state=' + (ConvertTo-LpString $state) + ',since=' + (ConvertTo-LpString $logon) + ',remote="-" ' + $ts)
        $rows++
    }
}
$lines += New-ExecRun 'host-session' $true $rows '' $ts
Write-LpLines $lines
exit 0
