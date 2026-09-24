---
name: "source-command-restart-data-path"
description: "Migrated source command `restart-data-path`"
---

# source-command-restart-data-path

Use this skill when the user asks to run the migrated source command `restart-data-path`.

## Command Template

# Restart Data Path

Restart the Telegraf container. (Grafana lives in `..\grafana`; its provisioning
reloads from files on its own, and `.env` changes need `docker compose up -d` there.)

## Usage
Use after Telegraf config changes.

## Command
```powershell
cd C:\Users\david\Repos\iot-backend; docker compose restart telegraf
```

## Notes
- Ensure `.env` is loaded by Docker compose.
- Check logs if restart fails.
