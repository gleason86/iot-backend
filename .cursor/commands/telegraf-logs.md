# Telegraf Logs (bounded)

Tail Telegraf logs with a bounded window.

## Usage
Use to debug parsing errors or pipeline issues.

## Command
```powershell
cd C:\Users\david\Repos\iot-backend; docker compose logs -f --tail=200 telegraf
```

## Notes
- Use Ctrl+C to stop streaming.
- Keep tail bounded to reduce noise.

