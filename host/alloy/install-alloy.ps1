# Grafana Alloy v1.19.2 on the Ryzen: attended install (household observability
# M3 pilot, CONTRACT.md / A 3.3, 7; decision D6; Codex C3 2026-09-16).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install-alloy.ps1 -Mode Preflight   (any user, read-only)
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install-alloy.ps1 -Mode Apply       (administrator)
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install-alloy.ps1 -Mode Rollback    (administrator)
#   ... any mode may add  -RuntimeAccount VirtualAccount|LocalSystem   (default VirtualAccount)
#
# Runtime identity (D6 amendment, Codex C3):
#   VirtualAccount  NT SERVICE\Alloy + Event Log Readers + read ACLs. The approved
#                   least-privilege path and the default. pfirewall.log carries a
#                   protected DACL re-authored by mpssvc (observed 2026-09-16); the
#                   pfirewall-acl.ps1 file grant is therefore PREDICTED (not yet
#                   observed) to disappear at the next rotation. That prediction is
#                   settled by running pfirewall-acl.ps1 -Mode Verify after a real
#                   rotation.
#   LocalSystem     Only for use AFTER a real rollover has demonstrably removed the
#                   virtual account's read access (a -Mode Verify transcript showing
#                   the Alloy SID without read on the new pfirewall.log and the winfw
#                   positions file not advancing). Apply then requires -Evidence
#                   <path to that transcript>, recorded in the install transcript.
#                   Because SYSTEM reads everything, the binaries, config, data and
#                   secrets are locked to SYSTEM + Administrators only (no user
#                   write anywhere Alloy reads from). No Network Configuration
#                   Operators membership, no WFP collection, in either path.
#
# Apply: downloads the release installer (SHA256 pinned below), installs the
# "Alloy" service pointing at C:\ProgramData\GrafanaLabs\Alloy\config.alloy,
# sets the runtime account, creates config/data/secrets with explicit ACLs,
# copies ca.crt and alloy-ryzen.password from the recovery-keys custody area
# (never printed), validates the config with the installed binary, starts the
# service and checks http://127.0.0.1:12345/-/ready. Rollback: stops and
# uninstalls the service and removes the group membership; data, secrets and
# backups stay. The pfirewall.log ACL and the audit settings are separate scripts.
# UpdateConfig (elevated, added 2026-09-17 for the gateway-pipeline fix): validates
# this directory's config.alloy with the installed binary, backs the installed
# config up under backups\, copies the new one (same ACL: the service SID keeps R),
# then POSTs /-/reload so the running service re-reads it WITHOUT a restart (no
# collector-restart mark, positions/bookmarks untouched). If the reload endpoint
# refuses, the previous config is restored and the transcript says so.
[CmdletBinding()]
param(
    [ValidateSet('Preflight', 'Apply', 'Rollback', 'UpdateConfig')][string]$Mode = 'Preflight',
    [ValidateSet('VirtualAccount', 'LocalSystem')][string]$RuntimeAccount = 'VirtualAccount',
    # LocalSystem Apply only: the pfirewall-acl.ps1 -Mode Verify transcript that
    # shows the virtual account lost read on pfirewall.log after a real rotation.
    [string]$Evidence = ''
)
$ErrorActionPreference = 'Stop'

$version = '1.19.2'
$installerUrl = "https://github.com/grafana/alloy/releases/download/v$version/alloy-installer-windows-amd64.exe"
$checksumsUrl = "https://github.com/grafana/alloy/releases/download/v$version/SHA256SUMS"
# From SHA256SUMS of the v1.19.2 release, read 2026-09-16 (alloy-installer-windows-amd64.exe).
$installerSha256 = '72b19a3f547a4d21b6c617e0934a8471fbce4867e03f65f1b49a42d23d378e36'
$serviceName = 'Alloy'
$virtualAccount = 'NT SERVICE\Alloy'
$serviceAccount = if ($RuntimeAccount -eq 'LocalSystem') { 'LocalSystem' } else { $virtualAccount }
$readersGroup = 'Event Log Readers'
$telegrafService = 'telegraf'
$programData = 'C:\ProgramData\GrafanaLabs\Alloy'
$configPath = Join-Path $programData 'config.alloy'
$dataDir = Join-Path $programData 'data'
$bookmarkDir = Join-Path $dataDir 'bookmarks'   # loki.source.windowsevent os.Create()s the bookmark file but never its parent
$secretsDir = Join-Path $programData 'secrets'
$backupDir = Join-Path $programData 'backups'
$installDir = Join-Path $env:ProgramFiles 'GrafanaLabs\Alloy'
$binary = Join-Path $installDir 'alloy-windows-amd64.exe'
$sourceConfig = Join-Path $PSScriptRoot 'config.alloy'
$secretsSource = 'C:\Users\david\.grafana-recovery-keys\household-gateway'
$secretFiles = @('ca.crt', 'alloy-ryzen.password')
$gatewayLogDir = 'C:\Users\david\Repos\grafana\pilot\logs\gateway'
$readyUrl = 'http://127.0.0.1:12345/-/ready'
$channels = @(
    'Security',
    'System',
    'Microsoft-Windows-TerminalServices-LocalSessionManager/Operational',
    'Microsoft-Windows-TerminalServices-RemoteConnectionManager/Operational',
    'Microsoft-Windows-RemoteDesktopServices-RdpCoreTS/Operational',
    'Microsoft-Windows-Windows Firewall With Advanced Security/Firewall'
)
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
# Identities allowed to hold write/modify/full on anything a LocalSystem Alloy reads.
$privilegedSids = @('S-1-5-18', 'S-1-5-32-544', 'S-1-3-0', 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')  # SYSTEM, Administrators, CREATOR OWNER, TrustedInstaller
$evidenceRequirement = @(
    'EVIDENCE REQUIREMENT for -RuntimeAccount LocalSystem (Codex C3): a pfirewall-acl.ps1 -Mode Verify',
    'transcript taken AFTER a real pfirewall.log rotation that followed pfirewall-acl.ps1 -Mode Apply,',
    'showing (a) the new pfirewall.log without a read ACE for the Alloy service SID and (b) the winfw',
    'positions file not advancing since that rotation. Pass it as -Evidence <path>; its path and sha256',
    'are recorded in the install transcript. Until such a transcript exists the virtual account stays.'
)

function Get-ServiceInfo {
    $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if (-not $svc) { return $null }
    $cim = Get-CimInstance Win32_Service -Filter "Name='$serviceName'" -ErrorAction SilentlyContinue
    [pscustomobject]@{ Status = $svc.Status; StartType = $svc.StartType; StartName = $cim.StartName; PathName = $cim.PathName }
}

function Test-ReadersMember {
    try {
        $members = Get-LocalGroupMember -Group $readersGroup -ErrorAction Stop
        return [bool]($members | Where-Object { $_.Name -eq $virtualAccount })
    } catch { return $null }
}

function Get-RegistryArguments {
    try { (Get-ItemProperty -Path 'HKLM:\SOFTWARE\GrafanaLabs\Alloy' -ErrorAction Stop).Arguments } catch { $null }
}

function Test-Ready {
    try { (Invoke-WebRequest -Uri $readyUrl -UseBasicParsing -TimeoutSec 5).Content.Trim() } catch { "not reachable ($($_.Exception.Message))" }
}

function Get-UnprivilegedWriters {
    # Allow ACEs granting write/modify/full to anyone outside SYSTEM/Administrators/
    # CREATOR OWNER/TrustedInstaller on a path a LocalSystem Alloy would read.
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    $acl = Get-Acl -LiteralPath $Path
    $writeMask = [System.Security.AccessControl.FileSystemRights]::WriteData -bor [System.Security.AccessControl.FileSystemRights]::AppendData -bor [System.Security.AccessControl.FileSystemRights]::WriteAttributes -bor [System.Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor [System.Security.AccessControl.FileSystemRights]::Delete -bor [System.Security.AccessControl.FileSystemRights]::ChangePermissions -bor [System.Security.AccessControl.FileSystemRights]::TakeOwnership
    $bad = @()
    foreach ($r in $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) {
        if ($r.AccessControlType -ne 'Allow') { continue }
        $sid = $r.IdentityReference.Value
        if ($privilegedSids -contains $sid) { continue }
        # Unsigned view of the mask so generic rights (GENERIC_ALL 0x10000000, GENERIC_WRITE 0x40000000) count too.
        $v = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$r.FileSystemRights), 0)
        if (($v -band [uint32]0x10000000) -or ($v -band [uint32]0x40000000) -or (($v -band [uint32]([int]$writeMask)) -ne 0)) {
            $name = try { $r.IdentityReference.Translate([System.Security.Principal.NTAccount]).Value } catch { $sid }
            $bad += "$name ($sid): $($r.FileSystemRights)"
        }
    }
    return $bad
}

function Show-Preflight {
    Write-Output "=== install-alloy.ps1 Preflight ($(Get-Date -Format s)) ==="
    Write-Output "Elevated: $isAdmin"
    Write-Output "Pinned: Alloy v$version, installer sha256 $installerSha256"
    Write-Output "Requested runtime account: $RuntimeAccount ($serviceAccount)"
    $info = Get-ServiceInfo
    if ($info) {
        Write-Output "Service '$serviceName': present, Status=$($info.Status), StartType=$($info.StartType), StartName=$($info.StartName)"
        if ($info.StartName -ne $serviceAccount) { Write-Output "  NOTE: configured StartName differs from the requested $serviceAccount (Apply refuses an existing service; Rollback first)" }
        Write-Output "  PathName: $($info.PathName)"
        Write-Output "  Registry Arguments: $(Get-RegistryArguments)"
        Write-Output "  Ready endpoint: $(Test-Ready)"
    } else {
        Write-Output "Service '$serviceName': absent"
    }
    $member = Test-ReadersMember
    if ($null -eq $member) { Write-Output "Group '$readersGroup': membership not readable ($virtualAccount)" }
    else { Write-Output "Group '$readersGroup' contains $virtualAccount : $member" }
    Write-Output "Install dir present: $(Test-Path -LiteralPath $installDir) ($installDir)"
    Write-Output "Binary present: $(Test-Path -LiteralPath $binary)"
    Write-Output "Config source present: $(Test-Path -LiteralPath $sourceConfig) ($sourceConfig)"
    Write-Output "Installed config present: $(Test-Path -LiteralPath $configPath)"
    Write-Output "Data dir present: $(Test-Path -LiteralPath $dataDir); bookmark dir present: $(Test-Path -LiteralPath $bookmarkDir)"
    foreach ($f in $secretFiles) {
        Write-Output "Secret source '$f' exists: $(Test-Path -LiteralPath (Join-Path $secretsSource $f)) (existence only)"
        Write-Output "Secret installed '$f' exists: $(Test-Path -LiteralPath (Join-Path $secretsDir $f))"
    }
    Write-Output "Gateway log dir present: $(Test-Path -LiteralPath $gatewayLogDir) ($gatewayLogDir)"
    Write-Output "Telegraf service present: $([bool](Get-Service -Name $telegrafService -ErrorAction SilentlyContinue)) (its read grant on $dataDir is re-applied by the LocalSystem ACL reset)"
    Write-Output '--- event channels (Get-WinEvent -ListLog) ---'
    foreach ($c in $channels) {
        try {
            $l = Get-WinEvent -ListLog $c -ErrorAction Stop
            Write-Output ("  {0}: IsEnabled={1} Records={2} MaxBytes={3} Mode={4}" -f $c, $l.IsEnabled, $l.RecordCount, $l.MaximumSizeInBytes, $l.LogMode)
        } catch {
            Write-Output "  ${c}: not readable without elevation ($($_.Exception.Message.Split([char]10)[0]))"
        }
    }
    Write-Output '--- pfirewall.log (profiles, cap, ACL) ---'
    try {
        Get-NetFirewallProfile | ForEach-Object { Write-Output ("  {0}: Enabled={1} LogBlocked={2} LogAllowed={3} LogMaxSizeKilobytes={4} LogFileName={5}" -f $_.Name, $_.Enabled, $_.LogBlocked, $_.LogAllowed, $_.LogMaxSizeKilobytes, $_.LogFileName) }
    } catch { Write-Output "  Get-NetFirewallProfile failed: $($_.Exception.Message)" }
    $logFile = Join-Path $env:SystemRoot 'System32\LogFiles\Firewall\pfirewall.log'
    foreach ($p in @($logFile, "$logFile.old")) {
        if (Test-Path -LiteralPath $p) {
            $item = Get-Item -LiteralPath $p
            Write-Output ("  {0}: {1} bytes, modified {2}" -f $p, $item.Length, $item.LastWriteTime.ToString('s'))
            try { $acl = Get-Acl -LiteralPath $p; $acl.Access | ForEach-Object { Write-Output ("    ACE {0} {1} {2} inherited={3}" -f $_.IdentityReference, $_.AccessControlType, $_.FileSystemRights, $_.IsInherited) } }
            catch { Write-Output '    ACL not readable without elevation' }
        } else { Write-Output "  ${p}: absent" }
    }
    Write-Output '  The protected DACL above is the observation; the loss of the pfirewall-acl.ps1 file grant at rotation is a'
    Write-Output '  prediction until pfirewall-acl.ps1 -Mode Verify after a real rotation shows it (Codex C3).'
    Write-Output '--- LocalSystem path: writable-by-non-admin check on what Alloy would read ---'
    foreach ($p in @($installDir, $programData)) {
        if (-not (Test-Path -LiteralPath $p)) { Write-Output "  ${p}: absent (created/checked at Apply)"; continue }
        try {
            $w = @(Get-UnprivilegedWriters $p)
            if ($w.Count -eq 0) { Write-Output "  ${p}: no non-admin write ACE" } else { Write-Output "  ${p}: NON-ADMIN WRITE PRESENT -> $($w -join '; ')" }
        } catch { Write-Output "  ${p}: ACL not readable ($($_.Exception.GetType().Name))" }
    }
    if ($RuntimeAccount -eq 'LocalSystem') {
        Write-Output '--- evidence ---'
        $evidenceRequirement | ForEach-Object { Write-Output "  $_" }
        if ($Evidence) { Write-Output "  -Evidence '$Evidence' exists: $(Test-Path -LiteralPath $Evidence)" } else { Write-Output '  -Evidence not given: Apply would refuse.' }
    } else {
        Write-Output "--- evidence: none needed for VirtualAccount; the LocalSystem fallback needs:"
        $evidenceRequirement | ForEach-Object { Write-Output "  $_" }
    }
    Write-Output "--- Apply would (RuntimeAccount=$RuntimeAccount) ---"
    Write-Output "  1. download $installerUrl to $env:TEMP and verify sha256 $installerSha256"
    Write-Output "  2. create $programData\{config.alloy,data,data\bookmarks,secrets,backups}; copy $sourceConfig to $configPath"
    Write-Output "  3. run the installer silently: /S /CONFIG=`"$configPath`" /DISABLEREPORTING=yes /DISABLEPROFILING=yes"
    if ($RuntimeAccount -eq 'LocalSystem') {
        Write-Output "  4. stop the service; keep the installer's LocalSystem StartName (no sc.exe config, no $readersGroup membership: SYSTEM already reads every channel)"
        Write-Output "  5. ACLs: $programData /inheritance:r SYSTEM:(OI)(CI)F Administrators:(OI)(CI)F, subtree /reset (inherits the same); re-grant $telegrafService read on data\ if that service exists, else print the icacls line;"
        Write-Output "     refuse if $installDir or $programData carries a non-admin write ACE"
        Write-Output "  6. copy $($secretFiles -join ', ') from $secretsSource to $secretsDir (never printed; SYSTEM/Administrators only)"
        Write-Output "  7. gateway log dir: no grant needed (SYSTEM has it)"
        Write-Output "  8. validate $configPath with $binary; start the service; assert StartName=LocalSystem; check $readyUrl"
        Write-Output "  9. record -Evidence path + sha256 in the transcript"
    } else {
        Write-Output "  4. stop the service; sc.exe config $serviceName obj= `"$serviceAccount`"; net localgroup `"$readersGroup`" `"$serviceAccount`" /add"
        Write-Output "  5. ACLs: data (M) and config (R) for $serviceAccount; secrets = SYSTEM/Administrators full + $serviceAccount read only"
        Write-Output "  6. copy $($secretFiles -join ', ') from $secretsSource to $secretsDir (never printed)"
        Write-Output "  7. grant $serviceAccount read on $gatewayLogDir (if it exists)"
        Write-Output "  8. validate $configPath with $binary; start the service; assert StartName=$serviceAccount; check $readyUrl"
    }
    Write-Output "  Rollback would: stop the service, run uninstall.exe /S, remove the $readersGroup membership if present; keep data, secrets, backups (and, after a LocalSystem Apply, the SYSTEM/Administrators-only ACL on $programData)."
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

function Get-ServiceSid {
    param([string]$Name = $serviceName)
    $ErrorActionPreference = 'Continue'
    $out = & sc.exe showsid $Name 2>&1
    $ErrorActionPreference = 'Stop'
    $line = $out | Where-Object { $_ -match 'SERVICE SID:\s*(S-1-5-80-\S+)' } | Select-Object -First 1
    if (-not $line) { throw "sc.exe showsid $Name did not return a SID" }
    return $Matches[1]
}

if ($Mode -eq 'Preflight') { Show-Preflight; exit 0 }
if (-not $isAdmin) { throw 'Run Apply/Rollback/UpdateConfig in an administrator PowerShell (Preflight is the non-elevated mode).' }
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Start-Transcript -Path (Join-Path $backupDir "install-$Mode-$RuntimeAccount-$stamp.log") | Out-Null
try {
    Write-Output "RuntimeAccount=$RuntimeAccount ($serviceAccount)"
    if ($Mode -eq 'UpdateConfig') {
        if (-not (Test-Path -LiteralPath $sourceConfig)) { throw "Missing $sourceConfig" }
        if (-not (Test-Path -LiteralPath $binary)) { throw "Alloy is not installed ($binary missing); run -Mode Apply" }
        $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if (-not $svc) { throw "Service '$serviceName' does not exist; run -Mode Apply" }
        $srcHash = (Get-FileHash -LiteralPath $sourceConfig -Algorithm SHA256).Hash
        $curHash = if (Test-Path -LiteralPath $configPath) { (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash } else { '-' }
        Write-Output "repo config sha256=$srcHash; installed sha256=$curHash"
        if ($srcHash -eq $curHash) { Write-Output 'Installed config already matches the repo; nothing to do.'; return }
        Invoke-Native $binary @('validate', $sourceConfig)
        Write-Output 'Repo config validated with the installed binary.'
        $prev = Join-Path $backupDir "config-before-updateconfig-$stamp.alloy"
        if (Test-Path -LiteralPath $configPath) { Copy-Item -LiteralPath $configPath -Destination $prev -Force; Write-Output "Installed config backed up to $prev" }
        Copy-Item -LiteralPath $sourceConfig -Destination $configPath -Force
        if ($RuntimeAccount -ne 'LocalSystem') { Invoke-Native 'icacls.exe' @($configPath, '/grant', "*$(Get-ServiceSid $serviceName):R") }
        $reloadOk = $false
        try {
            $r = Invoke-WebRequest -UseBasicParsing -Method POST -Uri 'http://127.0.0.1:12345/-/reload' -TimeoutSec 30
            Write-Output "POST /-/reload -> $($r.StatusCode) $(($r.Content | Out-String).Trim())"
            $reloadOk = ($r.StatusCode -eq 200)
        } catch { Write-Warning "reload failed: $($_.Exception.Message)" }
        if (-not $reloadOk) {
            if (Test-Path -LiteralPath $prev) { Copy-Item -LiteralPath $prev -Destination $configPath -Force; Write-Output 'Previous config restored (the running service never saw the new one).' }
            throw 'UpdateConfig aborted: the reload was refused; fix the config or use Restart-Service Alloy deliberately (that is a collector restart).'
        }
        Start-Sleep -Seconds 3
        Write-Output "Ready endpoint: $(Test-Ready)"
        Write-Output "UpdateConfig complete: installed sha256 now $((Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash); no service restart."
        return
    }
    if ($Mode -eq 'Rollback') {
        $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -ne 'Stopped') { Stop-Service -Name $serviceName -Force; Write-Output 'Service stopped.' }
        $uninstaller = Join-Path $installDir 'uninstall.exe'
        if (Test-Path -LiteralPath $uninstaller) {
            Start-Process -FilePath $uninstaller -ArgumentList '/S' -Wait -NoNewWindow
            Write-Output 'Uninstaller finished.'
        } elseif ($svc) {
            Invoke-Native 'sc.exe' @('delete', $serviceName)
        }
        if (Test-ReadersMember) { Invoke-Native 'net.exe' @('localgroup', $readersGroup, $virtualAccount, '/delete') }
        Write-Output "Rollback complete: service absent, group membership removed (if it existed). Kept: $dataDir, $secretsDir, $backupDir, $configPath."
    } else {
        if (-not (Test-Path -LiteralPath $sourceConfig)) { throw "Missing $sourceConfig" }
        foreach ($f in $secretFiles) {
            if (-not (Test-Path -LiteralPath (Join-Path $secretsSource $f))) { throw "Missing secret file $f under $secretsSource; run the gateway bootstrap first." }
        }
        if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) { throw "Service '$serviceName' already exists; run Rollback first or inspect it." }
        if ($RuntimeAccount -eq 'LocalSystem') {
            if (-not $Evidence -or -not (Test-Path -LiteralPath $Evidence)) {
                $evidenceRequirement | ForEach-Object { Write-Output $_ }
                throw 'LocalSystem needs -Evidence <path to the post-rotation pfirewall-acl.ps1 -Mode Verify transcript>; no change applied.'
            }
            $eh = (Get-FileHash -Algorithm SHA256 -LiteralPath $Evidence).Hash.ToLower()
            Write-Output "Evidence: $Evidence ($((Get-Item -LiteralPath $Evidence).Length) bytes, sha256 $eh)"
            $w = @(Get-UnprivilegedWriters $installDir)
            if ($w.Count) { throw "$installDir grants write to non-administrators ($($w -join '; ')); fix the ACL before a LocalSystem install. No change applied." }
        }

        # 1. Installer with pinned checksum.
        $installer = Join-Path $env:TEMP "alloy-installer-windows-amd64-v$version.exe"
        if (-not (Test-Path -LiteralPath $installer) -or (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLower() -ne $installerSha256) {
            Write-Output "Downloading $installerUrl"
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $installerUrl -OutFile $installer -UseBasicParsing
        }
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLower()
        if ($hash -ne $installerSha256) { Remove-Item -LiteralPath $installer -Force; throw "Installer checksum mismatch: $hash (expected $installerSha256, see $checksumsUrl); no change applied." }
        Write-Output "Installer checksum verified: $hash"

        # 2. Directories and the config file before the installer registers its arguments.
        foreach ($d in @($programData, $dataDir, $bookmarkDir, $secretsDir)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
        Copy-Item -LiteralPath $sourceConfig -Destination $configPath -Force
        Write-Output "Config copied to $configPath"

        # 3. Silent install (registers the service as LocalSystem and starts it against the real
        #    config for a few seconds until step 4 stops it). On a first install the secrets are
        #    not there yet, loki.write cannot build and nothing is shipped; after a Rollback the
        #    kept secrets\ makes that brief start ship as LocalSystem (the target identity of the
        #    LocalSystem path; a few seconds of SYSTEM-read entries on the VirtualAccount path).
        #    Positions/bookmark files created as SYSTEM receive the step 5 ACLs.
        $args = @('/S', "/CONFIG=`"$configPath`"", '/DISABLEREPORTING=yes', '/DISABLEPROFILING=yes')
        Write-Output "Running installer: $installer $($args -join ' ')"
        $proc = Start-Process -FilePath $installer -ArgumentList $args -Wait -PassThru -NoNewWindow
        if ($proc.ExitCode -ne 0) { throw "Installer exited with $($proc.ExitCode)" }
        Start-Sleep -Seconds 3
        if (-not (Get-Service -Name $serviceName -ErrorAction SilentlyContinue)) { throw "Service '$serviceName' not registered by the installer." }
        Write-Output "Registry Arguments: $(Get-RegistryArguments)"
        Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue

        if ($RuntimeAccount -eq 'LocalSystem') {
            # 4. Keep the installer's LocalSystem identity; no group membership (SYSTEM reads every channel).
            $info = Get-ServiceInfo
            if ($info.StartName -ne 'LocalSystem') { throw "Installer registered StartName=$($info.StartName), expected LocalSystem" }
            Write-Output 'Runtime account: LocalSystem (installer default kept; no Event Log Readers membership)'

            # 5. Protect everything Alloy reads: SYSTEM + Administrators only, no user write.
            #    C:\ProgramData's default DACL lets Users create files below it, which must not
            #    reach a config read by SYSTEM. /reset on each child (not the root, which would
            #    re-inherit from C:\ProgramData) makes the whole subtree inherit the new root ACL.
            Invoke-Native 'icacls.exe' @($programData, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)F', 'Administrators:(OI)(CI)F')
            foreach ($child in Get-ChildItem -LiteralPath $programData -Force) { Invoke-Native 'icacls.exe' @($child.FullName, '/reset', '/T', '/C') }
            $bad = @(Get-UnprivilegedWriters $programData) + @(Get-UnprivilegedWriters $installDir)
            if ($bad.Count) { throw "Non-admin write ACE remains: $($bad -join '; ')" }
            $tg = Get-Service -Name $telegrafService -ErrorAction SilentlyContinue
            if ($tg) {
                $tsid = Get-ServiceSid $telegrafService
                Invoke-Native 'icacls.exe' @($dataDir, '/grant', "*${tsid}:(OI)(CI)R")
                Write-Output "Re-granted NT SERVICE\$telegrafService ($tsid) read on $dataDir (source_progress)."
            } else {
                Write-Warning "Service $telegrafService absent: after install-telegraf.ps1, re-run  icacls `"$dataDir`" /grant `"NT SERVICE\${telegrafService}:(OI)(CI)R`"  (its step 5 does this)."
            }
        } else {
            # 4. Virtual account and Event Log Readers.
            Invoke-Native 'sc.exe' @('config', $serviceName, 'obj=', $serviceAccount)
            if (-not (Test-ReadersMember)) { Invoke-Native 'net.exe' @('localgroup', $readersGroup, $serviceAccount, '/add') }
            $sid = Get-ServiceSid
            Write-Output "Service SID: $sid"

            # 5. ACLs (grant by SID so the principal resolves regardless of service state).
            Invoke-Native 'icacls.exe' @($dataDir, '/grant', "*${sid}:(OI)(CI)M")
            Invoke-Native 'icacls.exe' @($configPath, '/grant', "*${sid}:R")
            Invoke-Native 'icacls.exe' @($secretsDir, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)F', 'Administrators:(OI)(CI)F', "*${sid}:(OI)(CI)R")
        }

        # 6. Secrets (existence only is ever printed).
        foreach ($f in $secretFiles) {
            Copy-Item -LiteralPath (Join-Path $secretsSource $f) -Destination (Join-Path $secretsDir $f) -Force
            Write-Output "Installed secret $f (length $((Get-Item -LiteralPath (Join-Path $secretsDir $f)).Length) bytes)"
        }

        # 7. Gateway log directory (bind mount of the log-gateway container).
        if ($RuntimeAccount -eq 'LocalSystem') {
            Write-Output "Gateway log dir: no grant needed for SYSTEM ($gatewayLogDir present: $(Test-Path -LiteralPath $gatewayLogDir))"
        } elseif (Test-Path -LiteralPath $gatewayLogDir) { Invoke-Native 'icacls.exe' @($gatewayLogDir, '/grant', "*${sid}:(OI)(CI)R") }
        else { Write-Warning "$gatewayLogDir does not exist yet; re-run the icacls grant after the gateway compose is up." }

        # 8. Validate, start, verify.
        Invoke-Native $binary @('validate', $configPath)
        Start-Service -Name $serviceName
        Start-Sleep -Seconds 5
        $info = Get-ServiceInfo
        Write-Output "Service: Status=$($info.Status) StartType=$($info.StartType) StartName=$($info.StartName)"
        if ($info.StartName -ne $serviceAccount) { throw "Service account is $($info.StartName), expected $serviceAccount" }
        $ready = Test-Ready
        Write-Output "Ready endpoint: $ready"
        if ($ready -notmatch 'ready') { throw 'Alloy did not report ready; inspect the Application event log (source Alloy) and the config.' }
        Write-Output "Group '$readersGroup' contains $virtualAccount : $(Test-ReadersMember)"
        if ($RuntimeAccount -eq 'LocalSystem') {
            Write-Output 'Applied as LocalSystem. Next: audit-settings.ps1 -Mode Apply (D5); pfirewall-acl.ps1 -Mode Verify, run ELEVATED from now on (the ProgramData tree is SYSTEM/Administrators only, so a non-elevated Verify cannot read positions or the Apply history), to confirm SYSTEM reads the log and the winfw positions advance; NT SERVICE\telegraf still needs its own read on the log for source_progress (pfirewall-acl.ps1). Binaries under Program Files keep the OS default (Users read/execute, no user write; checked before install).'
        } else {
            Write-Output 'Applied. Next: pfirewall-acl.ps1 -Mode Apply (log file ACL), audit-settings.ps1 -Mode Apply (D5), then verify streams in Loki and, after the first rotation, pfirewall-acl.ps1 -Mode Verify.'
        }
    }
} finally { Stop-Transcript | Out-Null }
