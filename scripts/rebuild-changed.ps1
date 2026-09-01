# Smart Rebuild Based on Code Changes
# Analyzes git changes and rebuilds only the services that need it

Write-Host "🔄 Smart Rebuild Analysis" -ForegroundColor Cyan
Write-Host "========================" -ForegroundColor Cyan
Write-Host ""

# Get the directory where this script is located (iot-backend root)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "📍 Working directory: $ProjectRoot" -ForegroundColor Gray
Write-Host ""

# Initialize analysis results
$analysis = @{
    changedFiles = @()
    servicesToRebuild = @()
    servicesToRestart = @()
    configChanges = @()
}

function Get-ChangedFiles {
    Write-Host "🔍 Analyzing git changes..." -ForegroundColor Yellow

    try {
        # Get changed files (staged + unstaged)
        $stagedChanges = git diff --cached --name-only 2>$null
        $unstagedChanges = git diff --name-only 2>$null

        $allChanges = $stagedChanges + $unstagedChanges | Where-Object { $_ } | Select-Object -Unique

        if ($allChanges.Count -eq 0) {
            Write-Host "  ℹ️ No changes detected in git" -ForegroundColor Gray
            return @()
        }

        Write-Host "  📝 Found $($allChanges.Count) changed files:" -ForegroundColor White
        $allChanges | ForEach-Object {
            Write-Host "    • $_" -ForegroundColor Gray
        }

        Write-Host ""
        return $allChanges
    }
    catch {
        Write-Host "  ❌ Could not analyze git changes: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "    Make sure you're in a git repository" -ForegroundColor Red
        return @()
    }
}
}

function Analyze-FileChanges {
    param([array]$changedFiles)

    Write-Host "🧠 Analyzing impact of changes..." -ForegroundColor Yellow

    $rebuildMap = @{
        # Services that need full rebuild (code changes)

        # Services that need rebuild for config changes
        "telegraf" = @("telegraf/telegraf.conf")
        "grafana" = @("grafana/**/*.json", "grafana/**/*.yaml", "grafana/**/*.yml")
        "mosquitto" = @("mosquitto/mosquitto.conf", "mosquitto/password.txt")

        # Infrastructure services (rarely need rebuild)
        "influxdb" = @("docker-compose.yml")
    }

    $restartMap = @{
        # Services that only need restart for config changes
        "telegraf" = @("telegraf/telegraf.conf")
        "grafana" = @("grafana/**/*.yaml", "grafana/**/*.yml")
        "mosquitto" = @("mosquitto/mosquitto.conf")
    }

    foreach ($file in $changedFiles) {
        $rebuildTriggered = $false

        # Check each service for rebuild requirements
        foreach ($service in $rebuildMap.Keys) {
            foreach ($pattern in $rebuildMap[$service]) {
                if ($file -like $pattern -or $file -match [regex]::Escape($pattern)) {
                    if ($analysis.servicesToRebuild -notcontains $service) {
                        $analysis.servicesToRebuild += $service
                        Write-Host "  🔨 $service needs rebuild (changed: $file)" -ForegroundColor Red
                        $rebuildTriggered = $true
                    }
                }
            }
        }

        # Check for restart-only changes
        if (-not $rebuildTriggered) {
            foreach ($service in $restartMap.Keys) {
                foreach ($pattern in $restartMap[$service]) {
                    if ($file -like $pattern -or $file -match [regex]::Escape($pattern)) {
                        if ($analysis.servicesToRestart -notcontains $service) {
                            $analysis.servicesToRestart += $service
                            Write-Host "  🔄 $service needs restart (changed: $file)" -ForegroundColor Yellow
                        }
                    }
                }
            }
        }

        # Check for configuration changes
        if ($file -like "*.yml" -or $file -like "*.yaml" -or $file -like "*.env") {
            $analysis.configChanges += $file
        }
    }

    Write-Host ""
}

function Execute-Rebuilds {
    Write-Host "🚀 Executing rebuilds..." -ForegroundColor Yellow

    # Rebuild services that need it
    if ($analysis.servicesToRebuild.Count -gt 0) {
        Write-Host "  🔨 Rebuilding services: $($analysis.servicesToRebuild -join ', ')" -ForegroundColor Red
        $rebuildCommand = "docker compose build $($analysis.servicesToRebuild -join ' ')"

        Write-Host "  Running: $rebuildCommand" -ForegroundColor Gray
        try {
            Invoke-Expression $rebuildCommand
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  ✅ Rebuild completed successfully" -ForegroundColor Green
            } else {
                Write-Host "  ❌ Rebuild failed with exit code $LASTEXITCODE" -ForegroundColor Red
                return $false
            }
        }
        catch {
            Write-Host "  ❌ Rebuild failed: $($_.Exception.Message)" -ForegroundColor Red
            return $false
        }
    }

    # Restart services that need it
    if ($analysis.servicesToRestart.Count -gt 0) {
        Write-Host "  🔄 Restarting services: $($analysis.servicesToRestart -join ', ')" -ForegroundColor Yellow
        $restartCommand = "docker compose restart $($analysis.servicesToRestart -join ' ')"

        Write-Host "  Running: $restartCommand" -ForegroundColor Gray
        try {
            Invoke-Expression $restartCommand
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  ✅ Restart completed successfully" -ForegroundColor Green
            } else {
                Write-Host "  ❌ Restart failed with exit code $LASTEXITCODE" -ForegroundColor Red
                return $false
            }
        }
        catch {
            Write-Host "  ❌ Restart failed: $($_.Exception.Message)" -ForegroundColor Red
            return $false
        }
    }

    return $true
}

function Show-Summary {
    Write-Host ""
    Write-Host "📊 Rebuild Summary" -ForegroundColor Cyan
    Write-Host "==================" -ForegroundColor Cyan

    if ($analysis.servicesToRebuild.Count -eq 0 -and $analysis.servicesToRestart.Count -eq 0) {
        Write-Host "  ✅ No services need rebuilding or restarting" -ForegroundColor Green
        Write-Host ""
        Write-Host "💡 Common next steps:" -ForegroundColor Cyan
        Write-Host "  • If you made code changes, commit them first: git add . && git commit -m 'your message'" -ForegroundColor White
        Write-Host "  • If services aren't behaving as expected, try: docker compose restart" -ForegroundColor White
        return
    }

    if ($analysis.servicesToRebuild.Count -gt 0) {
        Write-Host ""
        Write-Host "🔨 Rebuilt Services:" -ForegroundColor Red
        $analysis.servicesToRebuild | ForEach-Object {
            Write-Host "  • $_" -ForegroundColor Red
        }
    }

    if ($analysis.servicesToRestart.Count -gt 0) {
        Write-Host ""
        Write-Host "🔄 Restarted Services:" -ForegroundColor Yellow
        $analysis.servicesToRestart | ForEach-Object {
            Write-Host "  • $_" -ForegroundColor Yellow
        }
    }

    if ($analysis.configChanges.Count -gt 0) {
        Write-Host ""
        Write-Host "⚙️ Configuration Changes:" -ForegroundColor Blue
        $analysis.configChanges | ForEach-Object {
            Write-Host "  • $_" -ForegroundColor Blue
        }
    }

    Write-Host ""
    Write-Host "⏱️ Estimated Deployment Time:" -ForegroundColor White
    $rebuildTime = $analysis.servicesToRebuild.Count * 30  # ~30 seconds per service
    $restartTime = $analysis.servicesToRestart.Count * 5   # ~5 seconds per service
    $totalTime = $rebuildTime + $restartTime

    if ($totalTime -gt 0) {
        Write-Host "  $totalTime seconds" -ForegroundColor White
    }

    Write-Host ""
    Write-Host "✅ Smart rebuild completed!" -ForegroundColor Green
}

# Main execution
$changedFiles = Get-ChangedFiles

if ($changedFiles.Count -eq 0) {
    Show-Summary
    exit 0
}

Analyze-FileChanges -changedFiles $changedFiles

# Confirm before proceeding
if ($analysis.servicesToRebuild.Count -gt 0 -or $analysis.servicesToRestart.Count -gt 0) {
    Write-Host "🔍 Analysis complete. Ready to proceed with changes." -ForegroundColor Cyan
    Write-Host ""

    $confirmation = Read-Host "Continue with rebuild/restart? (y/N)"
    if ($confirmation -notmatch "^[Yy]$") {
        Write-Host "❌ Operation cancelled by user" -ForegroundColor Yellow
        exit 0
    }
    Write-Host ""
}

$success = Execute-Rebuilds

if ($success) {
    Show-Summary
} else {
    Write-Host ""
    Write-Host "❌ Rebuild failed!" -ForegroundColor Red
    Write-Host ""
    Write-Host "🔍 Try running diagnostics:" -ForegroundColor Yellow
    Write-Host "  .\.cursor\commands\troubleshoot-stack.md" -ForegroundColor White
    Write-Host ""
    Write-Host "📋 Or check service logs manually:" -ForegroundColor Yellow
    Write-Host "  docker compose logs <service_name>" -ForegroundColor White
    exit 1
}
}