# Restart Data Path

Restart Telegraf and Grafana containers.

## Usage
Use after Telegraf/Grafana config changes.

## Command
```powershell
cd C:\Users\david\Repos\iot-backend; docker compose restart telegraf grafana
```

## Notes
- Ensure `.env` is loaded by Docker compose.
- Check logs if restart fails.

