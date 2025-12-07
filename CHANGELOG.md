# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

