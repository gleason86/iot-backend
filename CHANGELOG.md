# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Verified encrypted InfluxDB/MQTT recovery, daily independent copies, a disabled
  native Threadripper standby, read-only freshness monitoring and disposable
  partition/crash/failback/buffer-full/disk-full drills. See the September 11
  recovery record for exact scope, credentials locations and remaining limits.

## [0.4.0] - 2026-09-08

### Removed
- **Grafana** moved to its own repo, `../grafana` (Grafana 13.2.1 on a fresh volume,
  joining `iot-backend_iot-network` as an external network). The `grafana` service,
  `grafana/` directory, `grafana_data` volume declaration and the `GRAFANA_*` /
  `INFLUXDB_READ_TOKEN` variables are gone from here. The old `iot-grafana`
  container was removed; the `iot-backend_grafana_data` volume is left for manual
  deletion. Reason: dashboards now span iot-backend, homeassistant and Networking.

### Security
- Grafana's read-only InfluxDB token replaced by one that also covers the `network`
  bucket (`grafana read-only (iot, network, voice_telemetry)`); the old
  `grafana read-only (iot, voice_telemetry)` auth deleted.

## [0.3.0] - 2026-08-31

### Removed
- **Voice assistant stack** (voice-gateway, voice-engine-1/2, voice-ui, chromadb,
  homeassistant-mcp, prometheus) — project parked; containers, images, volumes,
  networks, dashboards and Prometheus config removed. Code remains in `../voice_assistant`.
- Orphaned `emporia-import` / vuegraf service and volume.
- `DEPLOYMENT_PLAN.md` (described a server that does not exist).
- `GF_INSTALL_PLUGINS=grafana-clock-panel` — a failed plugin download/extract
  aborted Grafana startup; no dashboard used it.

### Security
- InfluxDB had been initialised with the example placeholders (`change_this_password`,
  `change_this_to_a_secure_token`) while `.env` held different values. Admin
  password reset to the `.env` value, admin token rotated (operator token), the
  placeholder token deleted. Telegraf and Grafana now use their own scoped tokens
  (`INFLUXDB_TELEGRAF_TOKEN` write-only, `INFLUXDB_READ_TOKEN` read-only) instead
  of the admin token.

### Fixed
- **Grafana ↔ InfluxDB**: the provisioned datasource carried a literal token that
  no longer matched the InfluxDB instance (re-initialised 2025-12-30), so every
  panel was unauthorized. The token now comes from `INFLUXDB_READ_TOKEN` (a
  read-only token scoped to the `iot`/`voice_telemetry` buckets) via the
  container environment; the dashboard's `${DS_INFLUXDB}` placeholders were
  replaced with the datasource uid so provisioning resolves them.
- **Log rotation** on every service (`x-logging` anchor, `10m` × 3) and as the
  Docker Desktop daemon default. An unrotated `voice-gateway` log had grown to
  1.04 TB (a WebSocket receive loop that never exited after client disconnect),
  filling the Docker VM disk on 2026-01-02 and crash-looping Grafana and
  Prometheus for eight months.

## [0.2.0] - 2025-12-15

### Added
- **Voice Assistant Integration**: Complete thin client voice assistant stack
  - Voice Gateway service (port 8766) for WebRTC/WebSocket routing
  - Voice Engine services (ports 8765, 8767) for STT/LLM/TTS processing
  - Voice UI web interface (port 3001) with React frontend
  - Prometheus monitoring (port 9090) for metrics collection
  - Home Assistant MCP server (port 4000) for voice control of smart home devices
  - ChromaDB integration (port 8000) for RAG functionality
- **Multi-Network Architecture**: Added voice-network for service isolation
- **Load Balancing**: Support for multiple voice engine instances
- **Health Checks**: Comprehensive health monitoring for all voice services
- **Documentation Validation**: Automated script to ensure docker-compose.yml matches README.md

### Architecture
- **Thin Client Model**: Centralized audio processing in Docker containers
- **Service Integration**: Unified deployment with existing IoT infrastructure
- **Production Ready**: Container orchestration with proper networking and volumes

## [0.1.1] - 2024-12-07

### Fixed
- Made all Telegraf JSON fields optional to handle both /data and /status MQTT topics
- Fixed Grafana datasource provisioning to use literal values instead of environment variables
- Fixed Grafana image tag (grafana:10 -> grafana:latest)

## [0.1.0] - 2024-12-06

### Added
- Initial project structure
- Docker Compose stack with:
  - Mosquitto MQTT broker (port 1883, 9001 for WebSocket)
  - InfluxDB v2 time-series database (port 8086)
  - Telegraf data pipeline (MQTT to InfluxDB)
  - Grafana visualization (port 3000)
- MQTT broker configuration with password authentication
- Telegraf configuration for JSON sensor data ingestion
- Pre-configured Grafana dashboard with:
  - Temperature time series and gauge
  - Humidity time series and gauge
  - Dew point tracking
  - Motion detection timeline
  - Multi-device filtering
- Grafana provisioning for automatic datasource and dashboard setup
- PowerShell setup scripts (`scripts/setup.ps1`, `start.ps1`, `stop.ps1`)
- Environment configuration template (`env.example.txt`)
- Comprehensive README with:
  - Architecture diagram
  - Quick start guide
  - MQTT topic structure
  - Home Assistant integration examples
  - Troubleshooting guide

### Arduino Integration
- Updated `DHT20_OLED.ino` with WiFi and MQTT support
- Added `config.h.example` for WiFi/MQTT credentials
- JSON payload publishing with temperature, humidity, dew point, motion
- Connection status indicators on OLED display
- Automatic WiFi and MQTT reconnection

