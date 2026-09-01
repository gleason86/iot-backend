# IoT Backend

Docker Compose stack on the Ryzen PC (`192.168.1.100`, static) that stores and
visualises home sensor data: an MQTT broker, InfluxDB, a Telegraf pipeline between
them, and Grafana. It is also the InfluxDB that Home Assistant (on the Pi,
`192.168.1.110`) mirrors its state history into.

> **History:** in Dec 2025 this repo also carried a voice-assistant stack (gateway,
> two engines, web UI, ChromaDB, a Home Assistant MCP bridge, Prometheus). That
> project is parked and the services were removed on 2026-08-31 — see CHANGELOG.
> The code still lives in `../voice_assistant`.

## Architecture

```
Arduino Uno R4 WiFi ──MQTT──▶ Mosquitto ──▶ Telegraf ──▶ InfluxDB ◀── Grafana
                                                             ▲
Home Assistant (Pi) ──influxdb: integration──────────────────┘
```

## Services

| Service   | Container       | Port        | Description                                   |
|-----------|-----------------|-------------|-----------------------------------------------|
| Mosquitto | `iot-mosquitto` | 1883 / 9001 | MQTT broker (password auth; 9001 = websockets) |
| InfluxDB  | `iot-influxdb`  | 8086        | InfluxDB 2.x, org `home`, bucket `iot`         |
| Telegraf  | `iot-telegraf`  | —           | MQTT `iot/sensors/+/{data,status}` → InfluxDB  |
| Grafana   | `iot-grafana`   | 3000        | Dashboards (provisioned from `grafana/`)       |

All services use rotated JSON logs (`10m` × 3) via the `x-logging` anchor in
`docker-compose.yml`. An unrotated log once grew to 1 TB and filled the Docker
VM disk — keep the anchor on every service.

## Quick start

```powershell
cp env.example.txt .env      # then fill in credentials
docker compose up -d
```

Grafana reads InfluxDB with `INFLUXDB_READ_TOKEN` (a read-only token). After the
first start, create one and add it to `.env`:

```powershell
docker exec iot-influxdb influx auth create --org home --read-bucket <iot bucket id> --description grafana
```

- **Grafana**: http://localhost:3000 (admin / see `.env`; anonymous viewers allowed)
- **InfluxDB**: http://localhost:8086
- Ports 3000 and 9090 are blocked from the LAN by Windows Firewall; 1883 and 8086
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
docker compose logs -f grafana       # provisioning errors
```

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
├── grafana/
│   ├── dashboards/iot/iot-sensors.json
│   └── provisioning/   # datasource + dashboard providers
└── scripts/            # setup / start / stop / troubleshoot (PowerShell)
```

## License

MIT
