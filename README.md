# IoT Backend

Verified independent InfluxDB/MQTT backups, a disabled Threadripper cold standby,
and read-only freshness monitoring are documented in
[recovery and continuity](docs/recovery-and-continuity-2026-09-11.md). Production
placement is unchanged; automatic failover is not enabled.

Docker Compose stack on the Ryzen PC (`192.168.1.100`, static) that stores home
sensor data: an MQTT broker, InfluxDB, and a Telegraf pipeline between them. It is
also the InfluxDB that Home Assistant (on the Pi, `192.168.1.110`) mirrors its state
history into, and that the Networking repo's modem poller writes to. Grafana, which
reads all of it, lives in its own repo: `../grafana` (since 2026-09-08).

> **History:** in Dec 2025 this repo also carried a voice-assistant stack (gateway,
> two engines, web UI, ChromaDB, a Home Assistant MCP bridge, Prometheus). That
> project is parked and the services were removed on 2026-08-31 — see CHANGELOG.
> The code still lives in `../voice_assistant`.

## Architecture

```
Arduino Uno R4 WiFi ──MQTT──▶ Mosquitto ──▶ Telegraf ──▶ InfluxDB ◀── Grafana (../grafana)
                                                             ▲
Home Assistant (Pi) ──influxdb: integration──────────────────┤
Networking/modem-status.py ──bucket network──────────────────┘
```

## Services

| Service   | Container       | Port        | Description                                   |
|-----------|-----------------|-------------|-----------------------------------------------|
| Mosquitto | `iot-mosquitto` | 1883 / 9001 | MQTT broker (password auth; 9001 = websockets) |
| InfluxDB  | `iot-influxdb`  | 8086        | InfluxDB 2.x, org `home`, buckets `iot`, `network`, `voice_telemetry` |
| Telegraf  | `iot-telegraf`  | —           | MQTT `iot/sensors/+/{data,status}` → InfluxDB  |

Grafana (`grafana`, port 3000) is run from `../grafana` and joins this stack's
`iot-backend_iot-network` as an external network. Start this stack first.

All services use rotated JSON logs (`10m` × 3) via the `x-logging` anchor in
`docker-compose.yml`. An unrotated log once grew to 1 TB and filled the Docker
VM disk — keep the anchor on every service.

## Quick start

```powershell
cp env.example.txt .env      # then fill in credentials
docker compose up -d
```

InfluxDB tokens are one per consumer, created with the operator token that stays
inside the container (the CLI profile there is stale and 401s without `-t`):

```powershell
docker exec iot-influxdb sh -c 'influx auth list -t "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"'
docker exec iot-influxdb sh -c 'influx auth create -o home -t "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" --write-bucket <bucket id> --description "<consumer> write-only, <bucket>"'
```

Current consumers: Telegraf (write `iot`), Home Assistant (write `iot`), the
Networking modem poller (write `network`), Grafana (read all; token kept in
`../grafana/.env`).

- **InfluxDB**: http://localhost:8086
- Port 3000 (Grafana) is blocked from the LAN by Windows Firewall; 1883 and 8086
  are reachable from the LAN (both require credentials).

## MQTT topics

Devices publish JSON to `iot/sensors/{device_id}/data` (readings) and
`iot/sensors/{device_id}/status` (online/offline). Telegraf maps the fields
listed in `telegraf/telegraf.conf` into the `sensor_data` measurement, tagged by
`device_id`. Example payload:

```json
{
  "device_id": "arduino-living-room",
  "temperature_f": 72.5,
  "temperature_c": 22.5,
  "humidity": 45.2,
  "dew_point_f": 50.1,
  "motion": false,
  "uptime_ms": 3600000
}
```

The Arduino must use the `MQTT_USER` / `MQTT_PASSWORD` from `.env` (the broker
rejects anonymous clients; a mismatch shows as `disconnected, not authorised` in
`docker compose logs mosquitto`).

## Home Assistant → InfluxDB

HA's `influxdb:` block (in the `homeassistant` repo, `config/configuration.yaml`)
writes `sensor`, `binary_sensor`, `climate`, `switch` and `light` state changes to
this instance: host `192.168.1.100`, port 8086, org `home`, bucket `iot`, token
from HA's `secrets.yaml`. Verify with:

```flux
from(bucket: "iot")
  |> range(start: -1h)
  |> filter(fn: (r) => exists r.entity_id)
  |> count()
```

## Troubleshooting

```powershell
docker compose ps
docker compose logs -f mosquitto     # client connects / auth failures
docker compose logs -f telegraf      # MQTT → Influx pipeline
```

Grafana problems: `cd ../grafana && python tools/grafana.py health`.

```flux
// Arduino data arriving?
from(bucket: "iot") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "sensor_data")
```

## Project structure

```
iot-backend/
├── docker-compose.yml
├── env.example.txt
├── mosquitto/          # mosquitto.conf, password.txt (gitignored) + example
├── telegraf/telegraf.conf
└── scripts/            # setup / start / stop / troubleshoot (PowerShell)
```

## License

MIT
