# Influx Quick Query

Run a short InfluxDB query for recent points.

## Usage
Use to verify data ingestion and field mapping.

## Command
```powershell
cd C:\Users\david\Repos\iot-backend; docker compose exec influxdb influx query 'from(bucket:"iot") |> range(start:-5m) |> limit(n:10)'
```

## Notes
- Requires Docker Desktop running.
- Use single quotes to avoid PowerShell interpolation of `|>`.

