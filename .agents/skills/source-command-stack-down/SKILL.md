---
name: "source-command-stack-down"
description: "Migrated source command `stack-down`"
---

# source-command-stack-down

Use this skill when the user asks to run the migrated source command `stack-down`.

## Command Template

# Stack Down

Stop and remove all IoT backend containers.

## Usage
Use when shutting down the stack.

## Command
```powershell
cd C:\Users\david\Repos\iot-backend; docker compose down
```

## Notes
- Requires Docker Desktop running.
- Volumes persist unless explicitly removed.
