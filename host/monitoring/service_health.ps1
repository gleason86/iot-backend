#Requires -Version 5.1
<#
.SYNOPSIS
Bounded read-only service health and dependency evaluator for the Ryzen (Windows
PowerShell 5.1 port of threadripper/scripts/monitoring/service_health.py).

.DESCRIPTION
Reads the same version-1 dependency manifest schema as the Threadripper and Pi
evaluators, runs allowlisted probes and prints the identical InfluxDB line protocol
(service_health, service_check, service_dependency; tags host=ryzen observer=ryzen
service; fields state_code impact_code age_seconds reason source_timestamp).
State/impact enum: 0 healthy, 1 degraded, 2 failed, 3 unknown, 4 intentionally
inactive. Stale or missing telemetry is unknown, never a carried-forward success.

Check types on Windows:
  http             GET, no redirects, no proxy, status code (allowlist http_hosts)
  tcp              TCP connect and close (allowlist tcp_hosts)
  scheduled_task   Get-ScheduledTask/Get-ScheduledTaskInfo: State, LastRunTime,
                   LastTaskResult, NextRunTime (allowlist scheduled_tasks)
  file_mtime       age of a regular file (allowlist file_paths)
  disk_free        System.IO.DriveInfo available bytes (allowlist disk_paths)
  windows_service  Get-Service status (allowlist windows_services)
  docker_container deliberately UNPROBED in this pilot: code 3, reason
                   "docker input omitted (D11)"; never drags a service with
                   other probed checks to unknown
  derived / probe_from=<other prober>   unprobed, evaluated elsewhere
  none             declared only

Runs as NT SERVICE\telegraf from a Telegraf inputs.exec (see ../telegraf/). Never
follows redirects, prints bodies, reads credentials or mutates anything. Probes run
sequentially under one wall-clock budget (no thread pool in PowerShell 5.1); the
Telegraf exec timeout must exceed budget_seconds.

.PARAMETER Command
evaluate (default), validate or topology.
.PARAMETER ManifestPath
Manifest JSON (default: C:\Users\david\Repos\iot-backend\config\monitoring\dependencies.json).
.PARAMETER OutFile
Write the line protocol to this file (UTF-8, LF) instead of stdout.
.PARAMETER Now
Fixed epoch seconds for reproducible runs.
.PARAMETER SelfTest
Run the deterministic fake-probe comparison against tests\expected.lp, then a live
structural run of tests\fixture-manifest.json. Exit code 0 only when both pass.
.PARAMETER CrossPort
Render -ManifestPath with the fake answers embedded in its "_fakes" block (http,
tcp, disk_free) at -Now; used by homeassistant/host/monitoring/tests/test_cross_port.py
to prove byte identity with the Python module.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File service_health.ps1 -SelfTest
powershell -NoProfile -ExecutionPolicy Bypass -File service_health.ps1 -Command validate -ManifestPath ..\..\config\monitoring\dependencies.json
#>
[CmdletBinding()]
param(
    [ValidateSet('evaluate', 'validate', 'topology')]
    [string]$Command = 'evaluate',
    [string]$ManifestPath = 'C:\Users\david\Repos\iot-backend\config\monitoring\dependencies.json',
    [string]$OutFile,
    [double]$Now = -1,
    [double]$BudgetSeconds = -1,
    [string]$HostName = 'ryzen',
    [string]$Observer = 'ryzen',
    [switch]$SelfTest,
    [switch]$WriteExpected,
    [switch]$CrossPort
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

# ----------------------------------------------------------------------------- constants
$HEALTHY = 0; $DEGRADED = 1; $FAILED = 2; $UNKNOWN = 3; $INACTIVE = 4
$SEVERITY = @{ 0 = 0.0; 4 = 0.5; 3 = 1.0; 1 = 2.0; 2 = 3.0 }
$DEPENDENCY_TYPES = @('hard', 'soft', 'batch')
$EXPECTED_STATES = @('active', 'scheduled', 'inactive', 'external')
$PROBE_TYPES = @('none', 'http', 'tcp', 'scheduled_task', 'file_mtime', 'disk_free', 'windows_service', 'docker_container', 'derived')
$SERVICE_ID = '^[a-z0-9][a-z0-9-]{0,47}$'
$CHECK_NAME = '^[a-z0-9_-]{1,32}$'
$HOST_LIKE = '^[a-z0-9.-]{1,63}$'
$TASK_NAME = '^[A-Za-z0-9][A-Za-z0-9 _.-]{0,119}$'
$SERVICE_NAME = '^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$'
$CONTAINER_NAME = '^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$'
# Superset of the Python REASON_ALLOWED: parentheses added for "docker input omitted (D11)".
$REASON_DISALLOWED = '[^A-Za-z0-9_:;,./=+>|() -]'
$MAX_REASON = 200
$MAX_BODY = 64 * 1024
$EVALUATOR_ID = 'health-evaluator'
$USER_AGENT = 'household-service-health/1'
$TASK_RESULT_RUNNING = 267009      # 0x41301
$TASK_RESULT_QUEUED = 267010       # 0x41302
$TASK_RESULT_NEVER_RAN = 267011    # 0x41303
$EPOCH = [DateTime]::new(1970, 1, 1, 0, 0, 0, [DateTimeKind]::Utc)

class ManifestError : System.Exception { ManifestError([string]$m) : base($m) {} }

# ----------------------------------------------------------------------------- helpers
function Get-Prop($obj, [string]$name, $default = $null) {
    if ($null -eq $obj) { return $default }
    if ($obj -is [System.Collections.IDictionary]) { if ($obj.Contains($name)) { return $obj[$name] } else { return $default } }
    $p = $obj.PSObject.Properties[$name]
    if ($null -eq $p) { return $default }
    return $p.Value
}
function Has-Prop($obj, [string]$name) {
    if ($null -eq $obj) { return $false }
    if ($obj -is [System.Collections.IDictionary]) { return $obj.Contains($name) }
    return $null -ne $obj.PSObject.Properties[$name]
}
function As-Array($value) { if ($null -eq $value) { return @() } else { return @($value) } }
function Is-Int($value) { return ($value -is [int] -or $value -is [long] -or $value -is [int16] -or $value -is [byte]) -and -not ($value -is [bool]) }
function To-Epoch([DateTime]$dt) { return [double](($dt.ToUniversalTime() - $EPOCH).TotalSeconds) }
function Real-Exception($err) {
    # PowerShell wraps .NET exceptions thrown by method calls; report the real one.
    while (($err -is [System.Management.Automation.MethodInvocationException] -or $err -is [System.Management.Automation.RuntimeException]) -and $null -ne $err.InnerException -and -not ($err -is [ManifestError])) { $err = $err.InnerException }
    return $err
}
function Short-Error($err) {
    # Fixed evaluator tokens pass through; anything else is only its type name.
    $err = Real-Exception $err
    $text = [string]$err.Message
    if ($err -is [ManifestError] -or $err -is [System.ArgumentException]) { if ($text -match '^[a-z_]{1,40}$') { return $text } }
    return $err.GetType().Name
}
function Worse([int]$first, [int]$second) { if ($SEVERITY[$second] -gt $SEVERITY[$first]) { return $second } else { return $first } }
function New-Result([int]$code, [string]$reason, $source = $null, $lastSuccess = $null, [bool]$unprobed = $false) {
    $r = @{ code = $code; reason = $reason; source = $source; last_success = $lastSuccess; unprobed = $unprobed }
    return $r
}

# ----------------------------------------------------------------------------- manifest
function Read-Manifest([string]$path) {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    $data = ConvertFrom-Json -InputObject $text
    Test-Manifest $data
    return $data
}

function Test-Manifest($data) {
    if ($null -eq $data -or (Get-Prop $data 'version') -ne 1) { throw [ManifestError]::new('manifest version must be 1') }
    foreach ($key in @('host', 'observer')) {
        $v = Get-Prop $data $key
        if (-not ($v -is [string]) -or $v -notmatch $HOST_LIKE) { throw [ManifestError]::new("manifest $key must be a short hostname-like string") }
    }
    $services = As-Array (Get-Prop $data 'services')
    if ($services.Count -eq 0) { throw [ManifestError]::new('manifest needs a non-empty services list') }
    $ids = @{}
    foreach ($service in $services) {
        $sid = Get-Prop $service 'id'
        if (-not ($sid -is [string]) -or $sid -notmatch $SERVICE_ID -or $sid -eq $EVALUATOR_ID) { throw [ManifestError]::new("invalid service id '$sid'") }
        if ($ids.ContainsKey($sid)) { throw [ManifestError]::new("duplicate service id $sid") }
        $ids[$sid] = $service
        if ($EXPECTED_STATES -notcontains (Get-Prop $service 'expected_state')) { throw [ManifestError]::new("${sid}: expected_state must be one of $($EXPECTED_STATES -join ', ')") }
        if ((Has-Prop $service 'unprobed') -and -not ((Get-Prop $service 'unprobed') -is [bool])) { throw [ManifestError]::new("${sid}: unprobed must be a boolean") }
        $checks = As-Array (Get-Prop $service 'checks')
        if ($checks.Count -eq 0) { throw [ManifestError]::new("${sid}: declare at least one check (type none is allowed)") }
        foreach ($check in $checks) {
            $type = Get-Prop $check 'type'
            if ($PROBE_TYPES -notcontains $type) { throw [ManifestError]::new("${sid}: unsupported check type '$type'") }
            if ([string](Get-Prop $check 'name' '') -notmatch $CHECK_NAME) { throw [ManifestError]::new("${sid}: each check needs a short name") }
            switch ($type) {
                'docker_container' { if ([string](Get-Prop $check 'container' '') -notmatch $CONTAINER_NAME) { throw [ManifestError]::new("${sid}: docker_container check needs a valid container name") } }
                'tcp' {
                    $port = Get-Prop $check 'port'
                    if (-not ((Get-Prop $check 'host') -is [string]) -or -not (Is-Int $port) -or $port -lt 1 -or $port -gt 65535) { throw [ManifestError]::new("${sid}: tcp check needs host and a port in 1-65535") }
                }
                'scheduled_task' { if ([string](Get-Prop $check 'task' '') -notmatch $TASK_NAME) { throw [ManifestError]::new("${sid}: scheduled_task check needs a task name") } }
                'windows_service' { if ([string](Get-Prop $check 'service' '') -notmatch $SERVICE_NAME) { throw [ManifestError]::new("${sid}: windows_service check needs a service name") } }
                'http' { if (-not ((Get-Prop $check 'url') -is [string])) { throw [ManifestError]::new("${sid}: http check needs a url") } }
                'file_mtime' { if (-not ((Get-Prop $check 'path') -is [string]) -or -not (Is-Int (Get-Prop $check 'max_age_seconds'))) { throw [ManifestError]::new("${sid}: file_mtime check needs path and max_age_seconds") } }
                'disk_free' { if (-not ((Get-Prop $check 'path') -is [string]) -or -not (Is-Int (Get-Prop $check 'failed_below_bytes'))) { throw [ManifestError]::new("${sid}: disk_free check needs path and failed_below_bytes") } }
            }
            if ((Has-Prop $check 'probe_from') -and ([string](Get-Prop $check 'probe_from' '') -notmatch $HOST_LIKE)) { throw [ManifestError]::new("${sid}: probe_from must be a short prober name") }
        }
        foreach ($dep in As-Array (Get-Prop $service 'depends_on')) {
            if ($DEPENDENCY_TYPES -notcontains (Get-Prop $dep 'type')) { throw [ManifestError]::new("${sid}: dependency type must be hard, soft or batch") }
            if ((Get-Prop $dep 'service') -eq $sid) { throw [ManifestError]::new("${sid}: self dependency") }
            $grace = Get-Prop $dep 'grace_seconds' 0
            if (-not (Is-Int $grace) -or $grace -lt 0) { throw [ManifestError]::new("${sid}: grace_seconds must be a non-negative integer") }
        }
    }
    foreach ($service in $services) {
        foreach ($dep in As-Array (Get-Prop $service 'depends_on')) {
            $up = Get-Prop $dep 'service'
            if (-not $ids.ContainsKey($up)) { throw [ManifestError]::new("$(Get-Prop $service 'id'): unknown upstream $up") }
            if ((Get-Prop $dep 'type') -eq 'hard' -and (Get-Prop $ids[$up] 'expected_state') -eq 'inactive') { throw [ManifestError]::new("$(Get-Prop $service 'id'): hard dependency on intentionally inactive $up") }
        }
    }
    $cycle = Find-Cycle $ids
    if ($cycle) { throw [ManifestError]::new('dependency cycle: ' + ($cycle -join ' -> ')) }
}

function Find-Cycle([hashtable]$ids) {
    $state = @{}
    $stack = New-Object System.Collections.ArrayList
    $script:cycleFound = $null
    function visit($node) {
        $state[$node] = 'visiting'
        [void]$stack.Add($node)
        foreach ($dep in As-Array (Get-Prop $ids[$node] 'depends_on')) {
            $target = Get-Prop $dep 'service'
            if ($state[$target] -eq 'visiting') {
                $idx = $stack.IndexOf($target)
                $script:cycleFound = @($stack.GetRange($idx, $stack.Count - $idx)) + @($target)
                return $true
            }
            if (-not $state.ContainsKey($target)) { if (visit $target) { return $true } }
        }
        $stack.RemoveAt($stack.Count - 1)
        $state[$node] = 'done'
        return $false
    }
    foreach ($node in @($ids.Keys)) {
        if (-not $state.ContainsKey($node)) { if (visit $node) { return $script:cycleFound } }
    }
    return $null
}

function Get-TopologicalOrder($services) {
    # $services: ordered list of service objects (manifest order, like Python's dict order)
    $ids = [ordered]@{}
    foreach ($s in $services) { $ids[(Get-Prop $s 'id')] = $s }
    $order = New-Object System.Collections.ArrayList
    $done = @{}
    function visit($node) {
        if ($done.ContainsKey($node)) { return }
        foreach ($dep in As-Array (Get-Prop $ids[$node] 'depends_on')) { visit (Get-Prop $dep 'service') }
        $done[$node] = $true
        [void]$order.Add($node)
    }
    foreach ($node in @($ids.Keys)) { visit $node }
    return @($order)
}

# ----------------------------------------------------------------------------- probe I/O boundary
# Overridden by -SelfTest with deterministic fakes. Nothing here is configurable
# from the manifest beyond allowlisted hosts, paths, task and service names.
$script:IO = @{
    Http = {
        param([string]$url, [double]$timeoutSeconds)
        $req = [System.Net.HttpWebRequest]::Create($url)
        $req.Method = 'GET'
        $req.Timeout = [int]($timeoutSeconds * 1000)
        $req.ReadWriteTimeout = [int]($timeoutSeconds * 1000)
        $req.AllowAutoRedirect = $false
        $req.Proxy = $null
        $req.KeepAlive = $false
        $req.UserAgent = $USER_AGENT
        $resp = $null
        try { $resp = $req.GetResponse() }
        catch [System.Net.WebException] {
            if ($null -ne $_.Exception.Response) { $resp = $_.Exception.Response } else { throw }
        }
        try {
            $status = [int]$resp.StatusCode
            $stream = $resp.GetResponseStream()
            $buffer = New-Object byte[] ($MAX_BODY + 1)
            $total = 0
            while ($total -lt $buffer.Length) {
                $n = $stream.Read($buffer, $total, $buffer.Length - $total)
                if ($n -le 0) { break }
                $total += $n
            }
            return @{ status = $status; body = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $total); length = $total }
        }
        finally { if ($resp) { $resp.Close() } }
    }
    Tcp = {
        param([string]$targetHost, [int]$port, [double]$timeoutSeconds)
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $ar = $client.BeginConnect($targetHost, $port, $null, $null)
            if (-not $ar.AsyncWaitHandle.WaitOne([int]($timeoutSeconds * 1000))) { throw [System.TimeoutException]::new('connect_timeout') }
            $client.EndConnect($ar)
            return $true
        }
        finally { $client.Close() }
    }
    Task = {
        param([string]$name, [string]$path)
        $task = Get-ScheduledTask -TaskName $name -TaskPath $path -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -InputObject $task -ErrorAction Stop
        return @{ state = [string]$task.State; last_run = $info.LastRunTime; last_result = [long]$info.LastTaskResult
                  next_run = $info.NextRunTime; missed = [long]$info.NumberOfMissedRuns }
    }
    FileMtime = {
        param([string]$path)
        $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw [System.ArgumentException]::new('symlink') }
        if ($item.PSIsContainer) { throw [System.ArgumentException]::new('not_regular') }
        return To-Epoch $item.LastWriteTimeUtc
    }
    DiskFree = {
        param([string]$path)
        $drive = New-Object System.IO.DriveInfo(($path -replace '/', '\'))
        return [long]$drive.AvailableFreeSpace
    }
    Service = {
        param([string]$name)
        $svc = Get-Service -Name $name -ErrorAction Stop
        return @{ status = [string]$svc.Status; start_type = [string]$svc.StartType }
    }
}

# ----------------------------------------------------------------------------- probes
function Probe-None($check, $ctx) { return New-Result $UNKNOWN (Get-Prop $check 'reason' 'no_probe_declared') }
function Probe-Derived($check, $ctx) { return New-Result $UNKNOWN ('derived:' + (([string](Get-Prop $check 'rule' 'rule')) -replace '[^a-z0-9_-]', '_')) $null $null $true }
function Probe-Delegated($check, $ctx) { return New-Result $UNKNOWN ('delegated:' + [string](Get-Prop $check 'probe_from')) $null $null $true }
function Probe-DockerContainer($check, $ctx) { return New-Result $UNKNOWN 'docker input omitted (D11)' $null $null $true }

function Probe-Http($check, $ctx) {
    $url = [string](Get-Prop $check 'url')
    try { $uri = [System.Uri]$url } catch { return New-Result $UNKNOWN 'url_not_allowlisted' }
    if (($uri.Scheme -ne 'http' -and $uri.Scheme -ne 'https') -or $uri.UserInfo -or ($ctx.http_hosts -notcontains $uri.Host)) { return New-Result $UNKNOWN 'url_not_allowlisted' }
    try { $answer = & $script:IO.Http $url $ctx.http_timeout }
    catch { return New-Result $FAILED ('unreachable:' + (Short-Error $_.Exception)) }
    $expected = As-Array (Get-Prop $check 'expect_status' @(200))
    if ($expected -notcontains $answer.status) { return New-Result $FAILED ('http_' + $answer.status) }
    $contains = Get-Prop $check 'json_contains'
    if ($null -eq $contains) { return New-Result $HEALTHY ('http_' + $answer.status) $ctx.now }
    try {
        if ($answer.length -gt $MAX_BODY) { throw [System.ArgumentException]::new('too_large') }
        $data = ConvertFrom-Json -InputObject $answer.body
        $items = $data
        foreach ($part in ([string](Get-Prop $contains 'list_path')).Split('.')) { $items = Get-Prop $items $part }
        $names = @()
        foreach ($item in As-Array $items) { $names += [string](Get-Prop $item (Get-Prop $contains 'item_key')) }
    }
    catch { return New-Result $UNKNOWN ('body_invalid:' + (Short-Error $_.Exception)) $ctx.now }
    $label = Get-Prop $contains 'label' 'item'
    if ($names -contains [string](Get-Prop $contains 'value')) { return New-Result $HEALTHY ('http_' + $answer.status + ';' + $label + '_present') $ctx.now }
    return New-Result ([int](Get-Prop $contains 'missing_code' $DEGRADED)) ('http_' + $answer.status + ';' + $label + '_missing') $ctx.now
}

function Probe-Tcp($check, $ctx) {
    $target = [string](Get-Prop $check 'host')
    if ($ctx.tcp_hosts -notcontains $target) { return New-Result $UNKNOWN 'host_not_allowlisted' }
    try { [void](& $script:IO.Tcp $target ([int](Get-Prop $check 'port')) $ctx.tcp_timeout) }
    catch { return New-Result $FAILED ('unreachable:' + (Short-Error $_.Exception)) }
    return New-Result $HEALTHY 'connected' $ctx.now
}

function Probe-ScheduledTask($check, $ctx) {
    $name = [string](Get-Prop $check 'task')
    if ($ctx.scheduled_tasks -notcontains $name) { return New-Result $UNKNOWN 'task_not_allowlisted' }
    $path = [string](Get-Prop $check 'task_path' '\')
    try { $info = & $script:IO.Task $name $path }
    catch {
        $type = (Real-Exception $_.Exception).GetType().Name
        if ($type -eq 'CimJobException' -or $_.Exception.Message -match 'No matching MSFT_ScheduledTask') { return New-Result $UNKNOWN 'task_missing' }
        return New-Result $UNKNOWN ('task_' + $type)
    }
    $expect = [string](Get-Prop $check 'expect' 'scheduled')
    $state = [string]$info.state
    if ($expect -eq 'disabled' -or $expect -eq 'inactive') {
        if ($state -eq 'Disabled') { return New-Result $INACTIVE 'disabled_as_expected' }
        return New-Result $DEGRADED ('unexpected_' + $state.ToLowerInvariant())
    }
    if ($state -eq 'Disabled') { return New-Result $FAILED 'task_disabled' }
    if ($state -eq 'Running' -or $info.last_result -eq $TASK_RESULT_RUNNING) { return New-Result $UNKNOWN 'running' }
    if ($info.last_result -eq $TASK_RESULT_QUEUED) { return New-Result $UNKNOWN 'queued' }
    $lastRun = $info.last_run
    if ($null -eq $lastRun -or -not ($lastRun -is [DateTime]) -or $lastRun.Year -lt 1971 -or $info.last_result -eq $TASK_RESULT_NEVER_RAN) { return New-Result $UNKNOWN 'never_ran' }
    $lastEpoch = To-Epoch $lastRun
    if ($lastEpoch - $ctx.now -gt $ctx.future_skew) { return New-Result $UNKNOWN 'future_timestamp' }
    $expectResult = [long](Get-Prop $check 'expect_result' 0)
    if ($info.last_result -ne $expectResult) { return New-Result $FAILED ('result_' + $info.last_result) $lastEpoch }
    $maxAge = Get-Prop $check 'max_age_seconds'
    if ((Is-Int $maxAge) -and ($ctx.now - $lastEpoch -gt [long]$maxAge)) { return New-Result $FAILED 'overdue' $lastEpoch $lastEpoch }
    return New-Result $HEALTHY 'ok' $lastEpoch $lastEpoch
}

function Probe-FileMtime($check, $ctx) {
    $path = [string](Get-Prop $check 'path')
    if ($ctx.file_paths -notcontains $path) { return New-Result $UNKNOWN 'path_not_allowlisted' }
    try {
        $mtime = & $script:IO.FileMtime $path
        if ($mtime - $ctx.now -gt $ctx.future_skew) { throw [System.ArgumentException]::new('future_timestamp') }
    }
    catch {
        $type = (Real-Exception $_.Exception).GetType().Name
        if ($type -eq 'ItemNotFoundException' -or $type -eq 'FileNotFoundException' -or $type -eq 'DirectoryNotFoundException') { return New-Result $UNKNOWN 'file_missing' }
        return New-Result $UNKNOWN ('file_' + (Short-Error $_.Exception))
    }
    if ($ctx.now - $mtime -gt [long](Get-Prop $check 'max_age_seconds')) { return New-Result $FAILED 'overdue' $mtime }
    return New-Result $HEALTHY 'ok' $mtime
}

function Probe-DiskFree($check, $ctx) {
    $path = [string](Get-Prop $check 'path')
    if ($ctx.disk_paths -notcontains $path) { return New-Result $UNKNOWN 'path_not_allowlisted' }
    try { $free = [long](& $script:IO.DiskFree $path) }
    catch { return New-Result $UNKNOWN ('disk_' + (Short-Error $_.Exception)) }
    $gib = [long][math]::Floor($free / 1GB)
    # Low free space is a capacity risk, not evidence the OS stopped: cap at degraded.
    if ($free -lt [long](Get-Prop $check 'failed_below_bytes')) { return New-Result $DEGRADED ("free_gib=$gib;exhausted") $ctx.now }
    if ($free -lt [long](Get-Prop $check 'degraded_below_bytes' 0)) { return New-Result $DEGRADED ("free_gib=$gib;low") $ctx.now }
    return New-Result $HEALTHY ("free_gib=$gib") $ctx.now
}

function Probe-WindowsService($check, $ctx) {
    $name = [string](Get-Prop $check 'service')
    if ($ctx.windows_services -notcontains $name) { return New-Result $UNKNOWN 'service_not_allowlisted' }
    try { $info = & $script:IO.Service $name }
    catch {
        $type = (Real-Exception $_.Exception).GetType().Name
        if ($type -eq 'ServiceCommandException' -or $_.Exception.Message -match 'ServiceCommandException|Cannot find any service') { return New-Result $UNKNOWN 'service_missing' }
        return New-Result $UNKNOWN ('service_' + $type)
    }
    $status = ([string]$info.status).ToLowerInvariant()
    $expect = ([string](Get-Prop $check 'expect' 'Running')).ToLowerInvariant()
    if ($expect -eq 'stopped' -or $expect -eq 'inactive') {
        if ($status -eq 'stopped') { return New-Result $INACTIVE 'stopped_as_expected' }
        return New-Result $DEGRADED ('unexpected_' + $status)
    }
    if ($status -eq 'running') { return New-Result $HEALTHY 'running' $ctx.now }
    return New-Result $FAILED ('service_' + $status)
}

function Get-ProbeFunction($check, $manifest) {
    $prober = Get-Prop $check 'probe_from'
    if ($prober -and $prober -ne (Get-Prop $manifest 'observer')) { return ${function:Probe-Delegated} }
    switch ([string](Get-Prop $check 'type')) {
        'none' { return ${function:Probe-None} }
        'http' { return ${function:Probe-Http} }
        'tcp' { return ${function:Probe-Tcp} }
        'scheduled_task' { return ${function:Probe-ScheduledTask} }
        'file_mtime' { return ${function:Probe-FileMtime} }
        'disk_free' { return ${function:Probe-DiskFree} }
        'windows_service' { return ${function:Probe-WindowsService} }
        'docker_container' { return ${function:Probe-DockerContainer} }
        'derived' { return ${function:Probe-Derived} }
    }
}

# ----------------------------------------------------------------------------- evaluation
function New-Context($manifest, [double]$now) {
    $allow = Get-Prop $manifest 'allowlist'
    $defaults = Get-Prop $manifest 'defaults'
    return @{
        now = $now
        http_hosts = @(As-Array (Get-Prop $allow 'http_hosts'))
        tcp_hosts = @(As-Array (Get-Prop $allow 'tcp_hosts'))
        file_paths = @(As-Array (Get-Prop $allow 'file_paths'))
        disk_paths = @(As-Array (Get-Prop $allow 'disk_paths'))
        scheduled_tasks = @(As-Array (Get-Prop $allow 'scheduled_tasks'))
        windows_services = @(As-Array (Get-Prop $allow 'windows_services'))
        http_timeout = [double](Get-Prop $defaults 'http_timeout_seconds' 5)
        tcp_timeout = [double](Get-Prop $defaults 'tcp_timeout_seconds' (Get-Prop $defaults 'http_timeout_seconds' 5))
        future_skew = [double](Get-Prop $defaults 'future_skew_seconds' 60)
    }
}

function Invoke-Checks($manifest, $ctx, [double]$budgetSeconds) {
    $outcomes = @{}
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    foreach ($service in As-Array (Get-Prop $manifest 'services')) {
        $sid = Get-Prop $service 'id'
        foreach ($check in As-Array (Get-Prop $service 'checks')) {
            $key = $sid + '|' + (Get-Prop $check 'name')
            if ($sw.Elapsed.TotalSeconds -gt $budgetSeconds) { $outcomes[$key] = New-Result $UNKNOWN 'probe_deadline'; continue }
            try { $outcomes[$key] = & (Get-ProbeFunction $check $manifest) $check $ctx }
            catch { $outcomes[$key] = New-Result $UNKNOWN ('probe_error:' + $_.Exception.GetType().Name) }
        }
    }
    return $outcomes
}

function Merge-Service($service, $outcomes) {
    $sid = Get-Prop $service 'id'
    $checks = @()
    foreach ($check in As-Array (Get-Prop $service 'checks')) { $checks += , $outcomes[$sid + '|' + (Get-Prop $check 'name')] }
    $counted = @($checks | ForEach-Object { -not $_.unprobed })
    if (-not ($counted -contains $true)) { $counted = @($checks | ForEach-Object { $true }) }
    $probed = @(); for ($i = 0; $i -lt $checks.Count; $i++) { if ($counted[$i]) { $probed += , $checks[$i] } }
    $code = $HEALTHY
    foreach ($item in $probed) { $code = Worse $code $item.code }
    $sources = @($probed | Where-Object { $null -ne $_.source } | ForEach-Object { [double]$_.source })
    $successes = @($probed | Where-Object { $null -ne $_.last_success } | ForEach-Object { [double]$_.last_success })
    $reasons = @()
    $names = @(As-Array (Get-Prop $service 'checks') | ForEach-Object { Get-Prop $_ 'name' })
    for ($i = 0; $i -lt $checks.Count; $i++) {
        if ($counted[$i] -and ($checks[$i].code -ne $HEALTHY -or $probed.Count -eq 1)) { $reasons += ($names[$i] + ':' + $checks[$i].reason) }
    }
    $reason = if ($reasons.Count) { $reasons -join ';' } else { 'ok' }
    $source = if ($sources.Count) { ($sources | Measure-Object -Minimum).Minimum } else { $null }
    $success = if ($successes.Count) { ($successes | Measure-Object -Minimum).Minimum } else { $null }
    $allUnprobed = (@($checks | Where-Object { -not $_.unprobed }).Count -eq 0)
    return @{ code = $code; reason = $reason; source = $source; checks = $checks; last_success = $success; all_unprobed = $allUnprobed }
}

function Get-Impact($manifest, $states, [double]$now) {
    $services = As-Array (Get-Prop $manifest 'services')
    $ids = @{}; foreach ($s in $services) { $ids[(Get-Prop $s 'id')] = $s }
    $impact = @{}; $effective = @{}; $edges = New-Object System.Collections.ArrayList
    $labels = @{ 2 = 'failed'; 1 = 'degraded'; 3 = 'unknown' }
    foreach ($sid in Get-TopologicalOrder $services) {
        $service = $ids[$sid]
        $worst = $HEALTHY; $notes = @()
        foreach ($dep in As-Array (Get-Prop $service 'depends_on')) {
            $upstream = Get-Prop $dep 'service'
            $upState = $states[$upstream]; $upEffective = $effective[$upstream]
            $depType = Get-Prop $dep 'type'
            $grace = [long](Get-Prop $dep 'grace_seconds' 0)
            $contribution = $HEALTHY
            if ($upEffective -eq $FAILED) {
                if ($depType -eq 'hard') { $contribution = $FAILED }
                else {
                    $success = $upState.last_success
                    $age = if ($null -ne $success) { $now - [double]$success } else { $null }
                    if ($null -eq $age -or $age -ge $grace) { $contribution = $DEGRADED } else { $notes += ('within_grace:' + $upstream) }
                }
            }
            elseif ($upEffective -eq $DEGRADED) {
                $contribution = if ($depType -eq 'hard') { $DEGRADED } else { $HEALTHY }
                if ($contribution -eq $HEALTHY) { $notes += ('upstream_degraded:' + $upstream) }
            }
            elseif ($upEffective -eq $UNKNOWN) {
                $upService = $ids[$upstream]
                $firstType = Get-Prop (@(As-Array (Get-Prop $upService 'checks'))[0]) 'type'
                # An upstream this host cannot probe at all (derived rule, delegated probe,
                # omitted Docker input per D11) is unverified here whatever its flag says
                # for the household evaluator, which evaluates it itself.
                $declaredUnprobed = [bool](Get-Prop $upService 'unprobed' ($firstType -eq 'none' -or $firstType -eq 'derived')) -or [bool]$upState.all_unprobed
                if ($declaredUnprobed) { $notes += ('unverified:' + $upstream) } else { $contribution = $UNKNOWN }
            }
            if ($contribution -ne $HEALTHY) { $notes += ($upstream + ':' + $labels[$contribution]) }
            [void]$edges.Add(@{ service = $sid; upstream = $upstream; type = $depType; upstream_state = $upState.code
                                upstream_effective = $upEffective; propagated = $contribution; grace_seconds = $grace })
            $worst = Worse $worst $contribution
        }
        $impact[$sid] = @{ code = $worst; reason = $(if ($notes.Count) { $notes -join ';' } else { 'none' }) }
        $observed = $states[$sid].code
        if ($observed -eq $INACTIVE) { $effective[$sid] = $INACTIVE }
        elseif ($observed -eq $FAILED -or $observed -eq $DEGRADED) { $effective[$sid] = $(if ($worst -ne $UNKNOWN) { Worse $observed $worst } else { $observed }) }
        elseif ($observed -eq $UNKNOWN) { $effective[$sid] = $(if ($worst -ne $HEALTHY) { $worst } else { $UNKNOWN }) }
        else { $effective[$sid] = $worst }
    }
    return @{ impact = $impact; edges = @($edges) }
}

function Invoke-Evaluate($manifest, $ctx, [double]$budgetSeconds) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $budget = if ($budgetSeconds -ge 0) { $budgetSeconds } else { [double](Get-Prop (Get-Prop $manifest 'defaults') 'budget_seconds' 20) }
    $outcomes = Invoke-Checks $manifest $ctx $budget
    $states = @{}
    foreach ($service in As-Array (Get-Prop $manifest 'services')) { $states[(Get-Prop $service 'id')] = Merge-Service $service $outcomes }
    $prop = Get-Impact $manifest $states $ctx.now
    return @{ states = $states; impact = $prop.impact; edges = $prop.edges; outcomes = $outcomes; duration_ms = [long]$sw.ElapsedMilliseconds }
}

# ----------------------------------------------------------------------------- line protocol
function Escape-Tag([string]$value) { return $value.Replace('\', '\\').Replace(',', '\,').Replace(' ', '\ ').Replace('=', '\=') }
function Escape-StringField([string]$value) { return '"' + $value.Replace('\', '\\').Replace('"', '\"') + '"' }
function Limit-Reason([string]$text) {
    $cleaned = ($text.Replace("`n", ' ').Replace("`r", ' ')) -replace $REASON_DISALLOWED, '_'
    if ($cleaned.Length -gt $MAX_REASON) { $cleaned = $cleaned.Substring(0, $MAX_REASON) }
    return $cleaned
}
function Format-Float([double]$value) {
    $text = $value.ToString('R', [System.Globalization.CultureInfo]::InvariantCulture)
    if ($text -notmatch '[.eE]') { $text += '.0' }
    return $text
}
function Sorted-Keys([hashtable]$table) {
    $keys = [string[]]@($table.Keys)
    [System.Array]::Sort($keys, [System.StringComparer]::Ordinal)
    return $keys
}
function New-Line([string]$measurement, [hashtable]$tags, [hashtable]$fields, [long]$timestampNs) {
    $tagText = ''
    foreach ($key in Sorted-Keys $tags) { $tagText += ',' + (Escape-Tag $key) + '=' + (Escape-Tag ([string]$tags[$key])) }
    $parts = @()
    foreach ($key in Sorted-Keys $fields) {
        $value = $fields[$key]
        if ($value -is [bool]) { $parts += (Escape-Tag $key) + '=' + $(if ($value) { 'true' } else { 'false' }) }
        elseif (Is-Int $value) { $parts += (Escape-Tag $key) + '=' + ([long]$value).ToString([System.Globalization.CultureInfo]::InvariantCulture) + 'i' }
        elseif ($value -is [double] -or $value -is [single] -or $value -is [decimal]) { $parts += (Escape-Tag $key) + '=' + (Format-Float ([double]$value)) }
        else { $parts += (Escape-Tag $key) + '=' + (Escape-StringField ([string]$value)) }
    }
    return (Escape-Tag $measurement) + $tagText + ' ' + ($parts -join ',') + ' ' + $timestampNs.ToString([System.Globalization.CultureInfo]::InvariantCulture)
}

function Format-Evaluation($manifest, $evaluation, $ctx) {
    $now = [double]$ctx.now
    $stamp = [long][math]::Floor($now * 1e9)
    $base = @{ host = [string](Get-Prop $manifest 'host'); observer = [string](Get-Prop $manifest 'observer') }
    $lines = New-Object System.Collections.ArrayList
    foreach ($service in As-Array (Get-Prop $manifest 'services')) {
        $sid = Get-Prop $service 'id'
        $state = $evaluation.states[$sid]; $impact = $evaluation.impact[$sid]
        $reason = $state.reason + $(if ($impact.code -ne $HEALTHY) { '|impact:' + $impact.reason } else { '' })
        $fields = @{ state_code = [long]$state.code; impact_code = [long]$impact.code; reason = (Limit-Reason $reason) }
        if ($null -ne $state.source) {
            $fields['source_timestamp'] = [long][math]::Truncate([double]$state.source)
            $fields['age_seconds'] = [long][math]::Max(0, [math]::Truncate($now - [double]$state.source))
        }
        $tags = $base.Clone(); $tags['service'] = $sid
        [void]$lines.Add((New-Line 'service_health' $tags $fields $stamp))
        $checks = @(As-Array (Get-Prop $service 'checks'))
        for ($i = 0; $i -lt $checks.Count; $i++) {
            $outcome = $state.checks[$i]
            $cf = @{ code = [long]$outcome.code; reason = (Limit-Reason $outcome.reason) }
            if ($null -ne $outcome.source) {
                $cf['source_timestamp'] = [long][math]::Truncate([double]$outcome.source)
                $cf['age_seconds'] = [long][math]::Max(0, [math]::Truncate($now - [double]$outcome.source))
            }
            $ct = $base.Clone(); $ct['service'] = $sid; $ct['check'] = [string](Get-Prop $checks[$i] 'name'); $ct['check_type'] = [string](Get-Prop $checks[$i] 'type')
            [void]$lines.Add((New-Line 'service_check' $ct $cf $stamp))
        }
    }
    foreach ($edge in $evaluation.edges) {
        $et = $base.Clone(); $et['service'] = $edge.service; $et['upstream'] = $edge.upstream; $et['dependency_type'] = $edge.type
        $ef = @{ declared = [long]1; upstream_state_code = [long]$edge.upstream_state; upstream_effective_code = [long]$edge.upstream_effective
                 propagated_code = [long]$edge.propagated; grace_seconds = [long]$edge.grace_seconds }
        [void]$lines.Add((New-Line 'service_dependency' $et $ef $stamp))
    }
    $unknown = @($evaluation.states.Values | Where-Object { $_.code -eq $UNKNOWN }).Count
    $unprobed = @($evaluation.outcomes.Values | Where-Object { $_.unprobed }).Count
    $summary = "ok;services=$($evaluation.states.Count);unknown=$unknown;duration_ms=$($evaluation.duration_ms)"
    if ($unprobed) { $summary += ";unprobed_checks=$unprobed" }
    $tags = $base.Clone(); $tags['service'] = $EVALUATOR_ID
    [void]$lines.Add((New-Line 'service_health' $tags @{ state_code = [long]$HEALTHY; impact_code = [long]$HEALTHY; source_timestamp = [long][math]::Truncate($now)
                                                         age_seconds = [long]0; reason = (Limit-Reason $summary) } $stamp))
    return @($lines)
}

function Format-EvaluatorFailure([string]$hostTag, [string]$observerTag, [string]$reason, [double]$now) {
    return @(New-Line 'service_health' @{ host = $hostTag; observer = $observerTag; service = $EVALUATOR_ID } `
        @{ state_code = [long]$FAILED; impact_code = [long]$UNKNOWN; source_timestamp = [long][math]::Truncate($now); age_seconds = [long]0; reason = (Limit-Reason $reason) } `
        ([long][math]::Floor($now * 1e9)))
}

function Get-Topology($manifest) {
    $nodes = @(); $edges = @()
    foreach ($service in As-Array (Get-Prop $manifest 'services')) {
        $sid = Get-Prop $service 'id'
        $firstType = Get-Prop (@(As-Array (Get-Prop $service 'checks'))[0]) 'type'
        $nodes += [ordered]@{ id = $sid; title = (Get-Prop $service 'title' $sid); subtitle = (Get-Prop $service 'owner' ''); kind = (Get-Prop $service 'kind' 'service')
                              expected_state = (Get-Prop $service 'expected_state'); schedule = (Get-Prop $service 'schedule' ''); runbook = (Get-Prop $service 'runbook' '')
                              unprobed = [bool](Get-Prop $service 'unprobed' ($firstType -eq 'none' -or $firstType -eq 'derived')) }
        foreach ($dep in As-Array (Get-Prop $service 'depends_on')) {
            $up = Get-Prop $dep 'service'
            $edges += [ordered]@{ id = "$up->$sid"; source = $up; target = $sid; type = (Get-Prop $dep 'type'); capability = (Get-Prop $dep 'capability' ''); grace_seconds = [long](Get-Prop $dep 'grace_seconds' 0) }
        }
    }
    return [ordered]@{ version = (Get-Prop $manifest 'version'); host = (Get-Prop $manifest 'host'); nodes = $nodes; edges = $edges }
}

function Write-Lines([string[]]$lines, [string]$outFile) {
    $text = ($lines -join "`n") + "`n"
    if ($outFile) {
        $tmp = $outFile + '.tmp'
        [System.IO.File]::WriteAllText($tmp, $text, (New-Object System.Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $tmp -Destination $outFile -Force
    }
    else { [Console]::Out.Write($text) }
}

function Get-NowEpoch { return [double]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) / 1000.0 }

# ----------------------------------------------------------------------------- self-test
function Say([string]$text) { [Console]::Out.WriteLine($text) }
function Invoke-SelfTest {
    $here = Split-Path -Parent $MyInvocation.ScriptName
    if (-not $here) { $here = $PSScriptRoot }
    $fixture = Join-Path $here 'tests\fixture-manifest.json'
    $expectedPath = Join-Path $here 'tests\expected.lp'
    $fixedNow = 1789511726.0
    $failures = 0
    Say "== self-test 1: deterministic fake probes vs tests\expected.lp (now=$fixedNow)"
    $manifest = Read-Manifest $fixture
    $saved = $script:IO.Clone()
    $script:IO.Http = {
        param($url, $t)
        switch ($url) {
            'http://localhost:3000/api/health' { return @{ status = 200; body = '{"database":"ok","version":"13.2.1"}'; length = 36 } }
            'http://127.0.0.1:8086/health' { return @{ status = 200; body = '{"status":"pass"}'; length = 17 } }
            'http://127.0.0.1:1/' { throw [System.Net.WebException]::new('refused') }
            'http://127.0.0.1:8123/api/' { return @{ status = 302; body = ''; length = 0 } }
            'http://127.0.0.1:11434/api/tags' { return @{ status = 200; body = '{"models":[{"name":"qwen3:14b-q4_K_M"}]}'; length = 40 } }
            default { throw [System.InvalidOperationException]::new("unexpected url $url") }
        }
    }
    $script:IO.Tcp = { param($h, $p, $t) if ($p -eq 1883) { return $true } else { throw [System.Net.Sockets.SocketException]::new(10061) } }
    $script:IO.Task = {
        param($name, $path)
        switch ($name) {
            'IoT Backend Verified Encrypted Recovery' { return @{ state = 'Ready'; last_run = ($EPOCH.AddSeconds($fixedNow - 3600)).ToLocalTime(); last_result = 0; next_run = $null; missed = 0 } }
            'Grafana Verified Encrypted Recovery' { return @{ state = 'Ready'; last_run = ($EPOCH.AddSeconds($fixedNow - 100000)).ToLocalTime(); last_result = 0; next_run = $null; missed = 0 } }
            'Networking nightly backup' { return @{ state = 'Ready'; last_run = ($EPOCH.AddSeconds($fixedNow - 120)).ToLocalTime(); last_result = 2147942402; next_run = $null; missed = 0 } }
            'Networking modem poll' { return @{ state = 'Disabled'; last_run = [DateTime]::new(1899, 12, 30); last_result = 267011; next_run = $null; missed = 0 } }
            default { throw [System.InvalidOperationException]::new('No matching MSFT_ScheduledTask objects found by CIM query') }
        }
    }
    $script:IO.FileMtime = { param($path) if ($path -like '*fixture-mtime.txt') { return $fixedNow - 30 } else { throw [System.Management.Automation.ItemNotFoundException]::new('missing') } }
    $script:IO.DiskFree = { param($path) return 64GB }
    $script:IO.Service = {
        param($name)
        switch ($name) {
            'W32Time' { return @{ status = 'Running'; start_type = 'Automatic' } }
            'com.docker.service' { return @{ status = 'Stopped'; start_type = 'Manual' } }
            'Alloy' { return @{ status = 'Stopped'; start_type = 'Manual' } }
            default { throw [System.Management.Automation.RuntimeException]::new('ServiceCommandException') }
        }
    }
    try {
        $ctx = New-Context $manifest $fixedNow
        $evaluation = Invoke-Evaluate $manifest $ctx 20
        $lines = Format-Evaluation $manifest $evaluation $ctx
    }
    finally { $script:IO = $saved }
    $normalize = { param($l) ($l -replace ' \d{19}$', ' <TS>') -replace 'duration_ms=\d+', 'duration_ms=<N>' }
    $got = @($lines | ForEach-Object { & $normalize $_ })
    if ($WriteExpected) {
        [System.IO.File]::WriteAllText($expectedPath, (($got -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
        Say "wrote $expectedPath ($($got.Count) lines)"
    }
    $expected = @([System.IO.File]::ReadAllText($expectedPath).Split("`n") | Where-Object { $_ -ne '' })
    $max = [math]::Max($got.Count, $expected.Count)
    $diff = 0
    for ($i = 0; $i -lt $max; $i++) {
        $g = if ($i -lt $got.Count) { $got[$i] } else { '<missing>' }
        $e = if ($i -lt $expected.Count) { $expected[$i] } else { '<missing>' }
        if ($g -cne $e) { $diff++; Say "DIFF line $($i + 1)`n  expected: $e`n  got:      $g" }
    }
    if ($diff -eq 0) { Say "PASS  $($got.Count) lines identical after timestamp normalization" } else { $failures++; Say "FAIL  $diff differing lines" }
    $states = @{}; foreach ($k in $evaluation.states.Keys) { $states[$k] = $evaluation.states[$k].code }
    $asserts = @(
        @('grafana healthy', ($states['grafana'] -eq $HEALTHY)),
        @('influxdb healthy despite unprobed docker_container + delegated http', ($states['influxdb'] -eq $HEALTHY)),
        @('mosquitto healthy via tcp', ($states['mosquitto'] -eq $HEALTHY)),
        @('iot-telegraf unknown (docker_container only, D11)', ($states['iot-telegraf'] -eq $UNKNOWN)),
        @('docker derived-only is unknown', ($states['docker'] -eq $UNKNOWN)),
        @('iot-recovery healthy (task ok 1h ago, file fresh)', ($states['iot-recovery'] -eq $HEALTHY)),
        @('grafana-recovery overdue is failed', ($states['grafana-recovery'] -eq $FAILED)),
        @('networking-backup nonzero result is failed', ($states['networking-backup'] -eq $FAILED)),
        @('modem-poll disabled as expected is inactive', ($states['modem-poll'] -eq $INACTIVE)),
        @('missing task and service are unknown', ($states['missing-task'] -eq $UNKNOWN -and $states['missing-service'] -eq $UNKNOWN)),
        @('w32time running', ($states['w32time'] -eq $HEALTHY)),
        @('docker-desktop-service stopped is failed', ($states['docker-desktop-service'] -eq $FAILED)),
        @('closed port is failed with no source', ($states['closed-port'] -eq $FAILED -and $null -eq $evaluation.states['closed-port'].source)),
        @('ha-remote wrong status is failed', ($states['ha-remote'] -eq $FAILED)),
        @('soft dependant of closed-port degraded without grace', ($evaluation.impact['soft-consumer'].code -eq $DEGRADED)),
        @('hard dependant of grafana-recovery failed', ($evaluation.impact['hard-consumer'].code -eq $FAILED)),
        @('consumer of unprobed lan and derived docker is healthy/unverified', ($evaluation.impact['grafana'].code -eq $HEALTHY -and $evaluation.impact['grafana'].reason -like '*unverified:lan*' -and $evaluation.impact['influxdb'].reason -like '*unverified:docker*'))
    )
    foreach ($a in $asserts) { if ($a[1]) { Say "PASS  $($a[0])" } else { $failures++; Say "FAIL  $($a[0])" } }

    Say "== self-test 2: live probes against tests\fixture-manifest.json (structure only; read-only)"
    $ctx = New-Context $manifest (Get-NowEpoch)
    $evaluation = Invoke-Evaluate $manifest $ctx -1
    $live = Format-Evaluation $manifest $evaluation $ctx
    $shape = '^[a-z_]+(,[a-z_]+=[^ ,]+)+ \S.* \d{19}$'
    $bad = @($live | Where-Object { $_ -notmatch $shape })
    $health = @($live | Where-Object { $_ -like 'service_health,*' })
    $services = @(As-Array (Get-Prop $manifest 'services')).Count
    $liveAsserts = @(
        @('every line matches the line-protocol shape', ($bad.Count -eq 0)),
        @("service_health rows = services + 1 ($($health.Count))", ($health.Count -eq $services + 1)),
        @('every row tagged host=ryzen,observer=ryzen', (@($live | Where-Object { $_ -notlike '*,host=ryzen,observer=ryzen,*' }).Count -eq 0)),
        @('evaluator row healthy', (@($health | Where-Object { $_ -like "*,service=$EVALUATOR_ID *" -and $_ -like '*state_code=0i*' }).Count -eq 1)),
        @('docker_container checks report the D11 reason', (@($live | Where-Object { $_ -like '*check_type=docker_container*' -and $_ -like '*docker input omitted (D11)*' }).Count -ge 1))
    )
    foreach ($a in $liveAsserts) { if ($a[1]) { Say "PASS  $($a[0])" } else { $failures++; Say "FAIL  $($a[0])" } }
    Say '-- live output'
    $live | ForEach-Object { Say $_ }
    Say "== self-test summary: failures=$failures"
    return $failures
}

# ----------------------------------------------------------------------------- main
if ($CrossPort) {
    $manifest = Read-Manifest $ManifestPath
    $fakes = Get-Prop $manifest '_fakes'
    $script:IO.Http = {
        param($url, $t)
        $answer = Get-Prop (Get-Prop $fakes 'http') $url
        if ($null -eq $answer) { throw [System.InvalidOperationException]::new("unexpected url $url") }
        $body = [string]$answer[1]
        return @{ status = [int]$answer[0]; body = $body; length = [System.Text.Encoding]::UTF8.GetByteCount($body) }
    }
    $script:IO.Tcp = { param($h, $p, $t) if (Get-Prop (Get-Prop $fakes 'tcp') "${h}:${p}") { return $true } else { throw [System.Net.Sockets.SocketException]::new(10061) } }
    $script:IO.DiskFree = { param($path) return [long](Get-Prop $fakes 'disk_free') }
    $script:IO.Task = { param($n, $p) throw [System.InvalidOperationException]::new('no command probes in the cross-port fixture') }
    $script:IO.Service = $script:IO.Task
    $script:IO.FileMtime = $script:IO.Task
    $fixedNow = if ($Now -ge 0) { $Now } else { Get-NowEpoch }
    $ctx = New-Context $manifest $fixedNow
    Write-Lines (Format-Evaluation $manifest (Invoke-Evaluate $manifest $ctx 20) $ctx) $OutFile
    exit 0
}
if ($SelfTest) {
    $f = [int](Invoke-SelfTest | Select-Object -Last 1)
    exit $(if ($f -eq 0) { 0 } else { 1 })
}
if ($Command -eq 'validate') {
    try { $manifest = Read-Manifest $ManifestPath }
    catch { [Console]::Error.WriteLine('invalid manifest: ' + $_.Exception.Message.Substring(0, [math]::Min($MAX_REASON, $_.Exception.Message.Length))); exit 1 }
    $edges = @((Get-Topology $manifest).edges).Count
    Write-Output "manifest valid: $(@(As-Array (Get-Prop $manifest 'services')).Count) services, $edges edges"
    exit 0
}
if ($Command -eq 'topology') {
    Write-Output (ConvertTo-Json (Get-Topology (Read-Manifest $ManifestPath)) -Depth 6)
    exit 0
}
$nowValue = if ($Now -ge 0) { $Now } else { Get-NowEpoch }
try { $manifest = Read-Manifest $ManifestPath }
catch {
    # Telegraf discards output of non-zero exits; report the failure as data instead.
    $real = Real-Exception $_.Exception
    Write-Lines (Format-EvaluatorFailure $HostName $Observer ('manifest_invalid:' + $real.GetType().Name + ':' + $real.Message) $nowValue) $OutFile
    exit 0
}
$ctx = New-Context $manifest $nowValue
$evaluation = Invoke-Evaluate $manifest $ctx $BudgetSeconds
Write-Lines (Format-Evaluation $manifest $evaluation $ctx) $OutFile
exit 0
