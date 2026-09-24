# Shared helpers for the Ryzen Telegraf exec scripts (dot-sourced; PowerShell 5.1).
# Deployed to C:\ProgramData\telegraf\exec\lp.ps1. Every script prints InfluxDB
# line protocol on stdout (UTF-8, no BOM, LF), exits 0 whenever it printed
# something useful (Telegraf discards the output of a non-zero exit) and ends with
# one exec_run row so "no rows" and "script failed" stay distinguishable.
$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $script:Utf8NoBom

function Get-NowNs { return [long]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) * 1000000 }
function ConvertTo-LpTag([string]$value) { return $value.Replace('\', '\\').Replace(',', '\,').Replace(' ', '\ ').Replace('=', '\=') }
function ConvertTo-LpString([string]$value) {
    $v = $value.Replace("`r", ' ').Replace("`n", ' ')
    return '"' + $v.Replace('\', '\\').Replace('"', '\"') + '"'
}
function ConvertTo-LpBool($value) { if ($value) { return 'true' } else { return 'false' } }
function ConvertTo-LpFloat([double]$value) {
    $t = $value.ToString('R', [System.Globalization.CultureInfo]::InvariantCulture)
    if ($t -notmatch '[.eE]') { $t += '.0' }
    return $t
}
function New-ExecRun([string]$script, [bool]$ok, [int]$rows, [string]$errorText, [long]$ts) {
    return 'exec_run,script=' + (ConvertTo-LpTag $script) + ' ok=' + (ConvertTo-LpBool $ok) + ',rows=' + $rows + 'i,error=' + (ConvertTo-LpString $errorText) + ' ' + $ts
}
function Write-LpLines([string[]]$lines) { if ($lines.Count) { [Console]::Out.Write((($lines -join "`n") + "`n")) } }
function Get-NativeOutput([string]$exe, [string[]]$arguments) {
    # Run a native command with stderr merged, without tripping ErrorActionPreference.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe; $psi.Arguments = ($arguments -join ' ')
    $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $out = $p.StandardOutput.ReadToEnd(); $err = $p.StandardError.ReadToEnd()
    $p.WaitForExit()
    return @{ exit = $p.ExitCode; stdout = $out; stderr = $err }
}
