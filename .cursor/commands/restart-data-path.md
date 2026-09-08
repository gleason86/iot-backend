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

