# IoT Backend

A Docker-based backend for collecting, storing, and visualizing IoT sensor data from Arduino devices. Includes vector database support for voice assistant RAG (Retrieval Augmented Generation).

## Architecture

```
Arduino Uno R4 WiFi ──MQTT──▶ Mosquitto ──▶ Telegraf ──▶ InfluxDB ◀── Grafana
                                │                            │
                                ▼                            ▼
                         Home Assistant ◀────────────────────┘
                                                             │
                                                             ▼
                         Voice Assistant ◀── ChromaDB (RAG) ─┘
```

## Services

| Service            | Port | Description                                  |
|--------------------|------|----------------------------------------------|
| Mosquitto          | 1883 | MQTT broker for device communication         |
| InfluxDB           | 8086 | Time-series database for sensor data         |
| Telegraf           | -    | MQTT to InfluxDB data pipeline               |
| Grafana            | 3000 | Visualization dashboards                     |
| ChromaDB           | 8000 | Vector database for voice assistant RAG      |
| HomeAssistant MCP  | 4000 | MCP server for voice assistant HA integration|

## Quick Start

### Prerequisites

- Docker Desktop with WSL2 backend
- Arduino Uno R4 WiFi (or compatible device)

### 1. Configure Environment

```bash
cp env.example.txt .env
# Edit .env with your credentials
```

### 2. Start Services

```bash
docker compose up -d
```

### 3. Access Dashboards

- **Grafana**: http://localhost:3000 (admin / see .env)
- **InfluxDB**: http://localhost:8086
- **ChromaDB**: http://localhost:8000/api/v1/heartbeat
- **MCP Server**: http://localhost:4000 (for voice assistant)

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

## ChromaDB Integration (Voice Assistant RAG)

The ChromaDB service provides vector storage for the voice assistant's adaptive learning system:

### Purpose
- Store embeddings of past voice interactions
- Enable semantic search for similar commands
- Support learning from user corrections

### Configuration

Add optional authentication in `.env`:
```env
CHROMA_SERVER_AUTH_CREDENTIALS=your-token-here
CHROMA_SERVER_AUTH_PROVIDER=chromadb.auth.token.TokenAuthServerProvider
```

### Voice Assistant Configuration

In your voice assistant, point to the ChromaDB server:
```yaml
vector_store:
  enabled: true
  provider: chromadb
  host: localhost  # or docker service name
  port: 8000
```

### API Examples

```bash
# Health check
curl http://localhost:8000/api/v1/heartbeat

# List collections
curl http://localhost:8000/api/v1/collections
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

## MCP Server (Voice Assistant Integration)

The HomeAssistant MCP (Model Context Protocol) server enables the voice assistant to control Home Assistant devices through a standardized tool interface.

### Configuration

Add your Home Assistant credentials to `.env`:

```env
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=your_long_lived_access_token_here
```

To generate a long-lived access token in Home Assistant:
1. Go to your Profile (bottom left)
2. Scroll to "Long-Lived Access Tokens"
3. Click "Create Token" and copy the value

### Voice Assistant Configuration

In your voice assistant's `config/mcp_servers.yaml`:

```yaml
mcp:
  enabled: true
  servers:
    home_assistant:
      transport: sse
      url: "http://localhost:4000/sse"
      enabled: true
```

### Available Tools

The MCP server provides 30+ tools for Home Assistant control:

| Category | Tools |
|----------|-------|
| Device Control | lights, climate, media_player, cover, lock, fan, vacuum |
| Automation | scenes, automations, scripts |
| System | device discovery, history, notifications |
| Smart Features | maintenance, smart scenarios |

### API Examples

```bash
# Health check
curl http://localhost:4000/health

# Check server info (if supported)
curl http://localhost:4000/
```

### Troubleshooting

```bash
# View MCP server logs
docker compose logs -f homeassistant-mcp

# Restart MCP server
docker compose restart homeassistant-mcp

# Check if Home Assistant is reachable from container
docker compose exec homeassistant-mcp curl -s $HOME_ASSISTANT_URL/api/
```

## Project Structure

```
iot-backend/
├── README.md
├── CHANGELOG.md
├── docker-compose.yml
├── env.example.txt
├── .cursor/
│   └── rules/
│       ├── iot_backend_rules.mdc    # Main coding standards
│       ├── data_schema.mdc          # Sensor data schema
│       └── security.mdc             # Security best practices
├── mosquitto/
│   ├── mosquitto.conf
│   └── password.txt.example
├── telegraf/
│   └── telegraf.conf
├── grafana/
│   ├── dashboards/
│   │   └── iot/
│   │       └── iot-sensors.json
│   └── provisioning/
│       ├── dashboards/
│       └── datasources/
└── scripts/
    ├── setup.ps1
    ├── start.ps1
    └── stop.ps1
```

## Troubleshooting

### Check service logs

```bash
docker compose logs -f mosquitto
docker compose logs -f telegraf
docker compose logs -f influxdb
docker compose logs -f grafana
docker compose logs -f chromadb
docker compose logs -f homeassistant-mcp
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

### Test ChromaDB

```bash
# Check if ChromaDB is running
curl http://localhost:8000/api/v1/heartbeat

# Should return: {"nanosecond heartbeat": <timestamp>}
```

## Service Management

```powershell
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart specific service
docker compose restart telegraf

# View real-time logs
docker compose logs -f

# Remove all data (reset)
docker compose down -v
```

## License

MIT
