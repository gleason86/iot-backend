# Documentation Validation

Validates documentation consistency between docker-compose.yml and README.md

```powershell
# Validate documentation consistency
.\scripts\validate-documentation.ps1

# For verbose output (shows all services found)
.\scripts\validate-documentation.ps1 -Verbose

# Note: Requires PowerShell YAML module
# Install with: Install-Module -Name powershell-yaml
```

This command validates that:
- All services in `docker-compose.yml` are documented in `README.md`
- All services documented in `README.md` exist in `docker-compose.yml`
- Port numbers are consistent between both files

Run this command to ensure documentation stays synchronized with the codebase.