---
name: "source-command-troubleshoot-stack"
description: "Migrated source command `troubleshoot-stack`"
---

# source-command-troubleshoot-stack

Use this skill when the user asks to run the migrated source command `troubleshoot-stack`.

## Command Template

# IoT Backend Stack Troubleshooting

Comprehensive diagnostic tool for identifying and resolving stack issues.

## Usage
Run full health check on all IoT backend services including connectivity, data flow, and error analysis.

## Command
```powershell
cd C:\Users\david\Repos\iot-backend; .\scripts\troubleshoot-stack.ps1
```

## Notes
- Requires Docker Desktop running and stack deployed
- Tests MQTT connectivity, data persistence, and service health
- Provides specific recommendations for any issues found
- Safe to run multiple times; creates minimal test data
