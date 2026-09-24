---
name: "source-command-stack-up"
description: "Migrated source command `stack-up`"
---

# source-command-stack-up

Use this skill when the user asks to run the migrated source command `stack-up`.

## Command Template

# Stack Up

Start all containers for the IoT backend.

## Usage
Use after environment changes or to bring the stack online.

## Command
```powershell
cd C:\Users\david\Repos\iot-backend; docker compose up -d
```

## Notes
- Requires Docker Desktop running and `.env` present.
- Uses `docker compose` (space), not `docker-compose`.
