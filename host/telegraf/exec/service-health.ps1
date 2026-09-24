#Requires -Version 5.1
<#
Telegraf inputs.exec wrapper for the Ryzen service-health evaluator
(../../monitoring/service_health.ps1 in the repo; C:\ProgramData\telegraf\monitoring\
service_health.ps1 when deployed). Runs the manifest at
C:\Users\david\Repos\iot-backend\config\monitoring\dependencies.json: the virtual
account NT SERVICE\telegraf needs Read on that directory (install-telegraf.ps1 grants
(OI)(CI)R on config\monitoring; the file is opened by full path, so no enumeration of
the parent directories is needed thanks to the default "Bypass traverse checking"
privilege held by Everyone). The evaluator writes its snapshot to
<StateDir>\service-health.lp (atomic rename) which is then printed; a crash of the
evaluator is reported as a service_health row for health-evaluator with
state_code=2, never as silence.
#>
[CmdletBinding()]
param(
    [string]$Manifest = 'C:\Users\david\Repos\iot-backend\config\monitoring\dependencies.json',
    [string]$StateDir = (Join-Path $env:ProgramData 'telegraf\state'),
    [double]$BudgetSeconds = 20
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lp.ps1')

$ts = Get-NowNs
function Failure([string]$reason) {
    $r = $reason -replace '[^A-Za-z0-9_:;,./=+>|() -]', '_'
    if ($r.Length -gt 200) { $r = $r.Substring(0, 200) }
    return @(('service_health,host=ryzen,observer=ryzen,service=health-evaluator age_seconds=0i,impact_code=3i,reason=' + (ConvertTo-LpString $r) + ',source_timestamp=' + [long]($ts / 1000000000) + 'i,state_code=2i ' + $ts),
             (New-ExecRun 'service-health' $false 0 $r $ts))
}
$candidates = @((Join-Path $PSScriptRoot '..\monitoring\service_health.ps1'), (Join-Path $PSScriptRoot '..\..\monitoring\service_health.ps1'))
$evaluator = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $evaluator) { Write-LpLines (Failure 'wrapper:evaluator_missing'); exit 0 }
try {
    if (-not (Test-Path -LiteralPath $StateDir)) { New-Item -ItemType Directory -Path $StateDir -Force | Out-Null }
    $snapshot = Join-Path $StateDir 'service-health.lp'
    & $evaluator -Command evaluate -ManifestPath $Manifest -BudgetSeconds $BudgetSeconds -OutFile $snapshot
    $out = @([System.IO.File]::ReadAllText($snapshot).Split("`n") | Where-Object { $_.Trim() })
    Write-LpLines ($out + @((New-ExecRun 'service-health' $true $out.Count '' $ts)))
}
catch {
    Write-LpLines (Failure ('wrapper:' + $_.Exception.GetType().Name + ':' + $_.Exception.Message))
}
exit 0
