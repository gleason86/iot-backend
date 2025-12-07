# IoT Backend

A Docker-based backend for collecting, storing, and visualizing IoT sensor data from Arduino devices.

## Architecture

```
Arduino Uno R4 WiFi ──MQTT──▶ Mosquitto ──▶ Telegraf ──▶ InfluxDB ◀── Grafana
                                │                            │
                                ▼                            ▼
                         Home Assistant ◀────────────────────┘
```

## Services

| Service    | Port | Description                          |
|------------|------|--------------------------------------|
| Mosquitto  | 1883 | MQTT broker for device communication |
| InfluxDB   | 8086 | Time-series database for sensor data |
| Telegraf   | -    | MQTT to InfluxDB data pipeline       |
| Grafana    | 3000 | Visualization dashboards             |

## Quick Start

### Prerequisites

- Docker Desktop with WSL2 backend
- Arduino Uno R4 WiFi (or compatible device)

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 2. Start Services

```bash
docker compose up -d
```

### 3. Access Dashboards

- **Grafana**: http://localhost:3000 (admin / see .env)
- **InfluxDB**: http://localhost:8086

### 4. Configure Arduino

1. Copy `config.h.example` to `config.h` in your Arduino sketch folder
2. Update WiFi and MQTT credentials
3. Upload sketch to Arduino

## MQTT Topics

Devices publish to structured topics:

```
iot/sensors/{device_id}/data    # JSON payload with all sensor readings
```

Example payload:
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

## Home Assistant Integration

### Option 1: MQTT Integration

Add to `configuration.yaml`:

```yaml
mqtt:
  sensor:
    - name: "Living Room Temperature"
      state_topic: "iot/sensors/arduino-living-room/data"
      value_template: "{{ value_json.temperature_f }}"
      unit_of_measurement: "°F"
      device_class: temperature

    - name: "Living Room Humidity"
      state_topic: "iot/sensors/arduino-living-room/data"
      value_template: "{{ value_json.humidity }}"
      unit_of_measurement: "%"
      device_class: humidity

  binary_sensor:
    - name: "Living Room Motion"
      state_topic: "iot/sensors/arduino-living-room/data"
      value_template: "{{ value_json.motion }}"
      payload_on: "true"
      payload_off: "false"
      device_class: motion
```

### Option 2: InfluxDB Integration

For historical data access, add the InfluxDB integration in Home Assistant.

## Project Structure

```
iot-backend/
├── README.md
├── CHANGELOG.md
├── docker-compose.yml
├── .env.example
├── mosquitto/
│   └── mosquitto.conf
├── telegraf/
│   └── telegraf.conf
└── grafana/
    └── dashboards/
        └── iot-sensors.json
```

## Troubleshooting

### Check service logs

```bash
docker compose logs -f mosquitto
docker compose logs -f telegraf
docker compose logs -f influxdb
docker compose logs -f grafana
```

### Test MQTT connection

```bash
# Subscribe to all topics (requires mosquitto-clients)
mosquitto_sub -h localhost -p 1883 -t "iot/#" -u mqtt_user -P your_password
```

### Verify data in InfluxDB

Access InfluxDB UI at http://localhost:8086 and query:

```flux
from(bucket: "iot")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "sensor_data")
```

## License

MIT


