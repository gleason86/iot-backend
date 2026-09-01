---
description: IoT Backend coding standards and data pipeline conventions
globs: "**/*.{yml,yaml,json,conf,toml}"
alwaysApply: true
---

# IoT Backend Rules

> **Related Rules Files:**
> - `../01-security-core/RULE.md` - Security best practices and secret management
> - `../04-testing-standards/RULE.md` - Testing patterns and coverage
> - `../05-logging-standards/RULE.md` - Logging patterns and monitoring
> - `../10-data-schema/RULE.md` - Sensor data schema definitions
> - `../20-error-handling/RULE.md` - Error handling and data loss prevention
> - `../80-self-improvement/RULE.md` - Self-improvement and maintenance rules
> - `../99-cross-repo/RULE.md` - Cross-repository coordination

---

## Project Architecture

```
┌─────────────────┐     ┌───────────────┐     ┌──────────────┐     ┌───────────────┐     ┌───────────────┐
│  Arduino/IoT    │────▶│   Mosquitto   │────▶│   Telegraf   │────▶│   InfluxDB    │────▶│    Grafana    │
│    Devices      │     │  MQTT Broker  │     │   Pipeline   │     │   Database    │     │  Dashboards   │
└─────────────────┘     └───────────────┘     └──────────────┘     └───────────────┘     └───────────────┘
     (upstream)                                                           │                    │
                                                                          ▼                    ▼
                        ┌───────────────┐                         ┌───────────────┐     ┌───────────────┐
                        │   ChromaDB    │◀────────────────────────│ Voice Engines │◀────│ Voice Gateway │
                        │  Vector Store │                         │  STT/LLM/TTS  │     │ WebRTC/WS     │
                        └───────────────┘                         └───────────────┘     └───────────────┘
                                                                                                │
                                                                                                ▼
                                                                                         ┌───────────────┐
                                                                                         │   Voice UI    │
                                                                                         │   React App   │
                                                                                         └───────────────┘
                                                                                                │
                                                                                                ▼
                                                                                         ┌───────────────┐
                                                                                         │  Prometheus   │
                                                                                         │   Monitoring  │
                                                                                         └───────────────┘
```

### Component Locations
| Component | Location | Purpose |
|-----------|----------|---------|
| IoT Device Code | `../Arduino/` | Sensor firmware (separate repo) |
| MQTT Broker | `mosquitto/mosquitto.conf` | Device communication |
| Data Pipeline | `telegraf/telegraf.conf` | MQTT → InfluxDB |
| Database | InfluxDB (docker-compose.yml) | Time-series storage |
| Dashboards | `grafana/dashboards/*.json` | Visualization |
| Vector Store | ChromaDB (docker-compose.yml) | Voice assistant RAG |
| Voice Gateway | voice-gateway (docker-compose.yml) | WebRTC/WebSocket router |
| Voice Engines | voice-engine-* (docker-compose.yml) | STT/LLM/TTS processing |
| Voice UI | voice-ui (docker-compose.yml) | Web interface |
| Monitoring | Prometheus (docker-compose.yml) | Metrics collection |
| Infrastructure | `docker-compose.yml` | Container orchestration |

---

## Cross-Repository Integration

> **Voice Assistant Repository**: Voice services deployed via this docker-compose.yml.
> See `../voice_assistant/.cursor/rules/00-core/RULE.md` for voice assistant development patterns.
>
> **ADR Reference**: See ADR-022 in voice_assistant/docs/architecture/adr/ for integration decision rationale.

### Shared Infrastructure
- **ChromaDB**: Used by voice assistant for RAG (Retrieval Augmented Generation)
- **Home Assistant MCP**: Enables voice control of smart home devices
- **Prometheus**: Unified monitoring for both IoT and voice services
- **Networking**: Shared container networks for inter-service communication

### Development Coordination
- Voice assistant development occurs in separate repository
- IoT backend provides infrastructure orchestration
- Changes to shared services require coordination between repositories
- Documentation updates must be synchronized

### Voice Assistant Integration
- **Thin Client Architecture**: Voice processing centralized in containers
- **Load Balancing**: Multiple voice-engine services for scalability
- **WebRTC/WebSocket Transport**: Real-time audio streaming
- **MCP Integration**: Home Assistant control via Model Context Protocol
- **RAG Support**: ChromaDB provides context for intelligent responses
- **Prometheus Monitoring**: Metrics collection for voice services

---

## File-Specific Guidelines

### docker-compose.yml
- Environment variables for credentials use `.env` file
- Volume mounts for config files should be read-only (`:ro`)
- Service dependencies must reflect data flow order
- Use named volumes for data persistence
- Always set `restart: unless-stopped` for production services

### telegraf/telegraf.conf
- Each JSON field from IoT devices must have a corresponding field definition
- Use `optional = true` for all fields (devices may not send all fields)
- Tags are indexed; use sparingly (device_id, location, etc.)
- Fields are not indexed; use for measurements (temperature, humidity, etc.)

### grafana/dashboards/*.json
- All panels querying sensor data must use measurement `sensor_data`
- Use template variable `${device:regex}` for device filtering
- Queries should use `aggregateWindow()` for time-series panels
- Use consistent color schemes across related metrics

### mosquitto/mosquitto.conf
- Always enable authentication for production
- Configure persistence for message durability
- Set appropriate QoS levels for sensor data

---

## Common Flux Query Patterns

### Query a specific field
```flux
from(bucket: "iot")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "sensor_data")
  |> filter(fn: (r) => r._field == "temperature_f")
  |> filter(fn: (r) => r.device_id =~ /${device:regex}/)
```

### Get latest value
```flux
from(bucket: "iot")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "sensor_data")
  |> filter(fn: (r) => r._field == "humidity")
  |> last()
```

### Aggregate for time-series
```flux
from(bucket: "iot")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "sensor_data")
  |> filter(fn: (r) => r._field == "dew_point_f")
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
```

---

## Quick Commands

```powershell
# Restart services after config changes
docker compose restart telegraf grafana

# View Telegraf logs for parsing errors
docker compose logs -f telegraf

# Test MQTT message manually
mosquitto_pub -h localhost -p 1883 -u $MQTT_USER -P $MQTT_PASSWORD -t "iot/sensors/test/data" -m '{"device_id":"test","temperature_f":72.5,"humidity":45.0}'

# Query InfluxDB directly
docker compose exec influxdb influx query 'from(bucket:"iot") |> range(start:-1h) |> limit(n:10)'

# Check ChromaDB health
curl http://localhost:8000/api/v1/heartbeat
```

## Validation Checklist

Before committing changes that affect data structure:

- [ ] Telegraf config has field definition for all IoT payload fields
- [ ] Field types match between IoT device code and Telegraf config
- [ ] Grafana dashboards can query all stored fields
- [ ] No orphaned dashboard panels querying removed fields
- [ ] CHANGELOG.md updated with schema changes
- [ ] Restart containers to apply config changes

---

## Cursor Commands
- Location: `.cursor/commands/` (pinned to repo path).
- Available commands:
  - `stack-up.md` — `docker compose up -d`
  - `stack-down.md` — `docker compose down`
  - `restart-data-path.md` — restart Telegraf + Grafana
  - `telegraf-logs.md` — bounded tail of Telegraf logs
  - `influx-query.md` — quick Flux query (last 5m, 10 rows)
  - `chromadb-health.md` — heartbeat check
  - `voice-health.md` — voice service health checks
  - `voice-logs.md` — voice service log tailing
  - `voice-restart.md` — voice service restart
  - `validate-docs.md` — documentation validation

## PowerShell Gotchas
- Use `;` for chaining (not `&&`).
- Use `docker compose` (space) not `docker-compose` (deprecated).
- Flux queries: wrap in single quotes to avoid `|>` interpolation.
- Keep log tails bounded (`--tail=200`) to avoid huge outputs.
- Ensure Docker Desktop is running; otherwise compose/exec will fail.

---

## Validation Checklist

Before committing changes that affect data structure:

- [ ] Telegraf config has field definition for all IoT payload fields
- [ ] Field types match between IoT device code and Telegraf config
- [ ] Grafana dashboards can query all stored fields
- [ ] No orphaned dashboard panels querying removed fields
- [ ] CHANGELOG.md updated with schema changes
- [ ] Restart containers to apply config changes