---
description: Logging and observability patterns for IoT data pipeline monitoring
globs: "**/*.{yml,yaml,conf,py,sh,ps1}"
alwaysApply: true
---

# IoT Logging & Observability Standards

> **Related Rules Files:**
> - `../00-iot-backend-core/RULE.md` - Core architecture and infrastructure
> - `../04-testing-standards/RULE.md` - Testing patterns and validation
> - `../20-error-handling/RULE.md` - Error handling and recovery
> - `../80-self-improvement/RULE.md` - Logging maintenance guidelines

---

## Logging Architecture

### Log Levels and Purposes

| Level | Purpose | Examples |
|-------|---------|----------|
| **ERROR** | System failures requiring immediate attention | MQTT broker disconnection, InfluxDB write failures, data loss |
| **WARNING** | Potential issues or degraded performance | High latency, partial failures, resource constraints |
| **INFO** | Normal operations and state changes | Service startup, successful data ingestion, configuration reloads |
| **DEBUG** | Detailed diagnostic information | Individual message processing, parsing details, performance metrics |

### Structured Logging Format
```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "service": "telegraf",
  "component": "mqtt_consumer",
  "device_id": "sensor_001",
  "message": "Processed sensor data",
  "fields": {
    "temperature_f": 72.5,
    "humidity": 45.0,
    "processing_time_ms": 15
  },
  "trace_id": "abc123"
}
```

---

## Service-Specific Logging

### MQTT Broker (Mosquitto) Logging
```conf
# mosquitto.conf
log_type error
log_type warning
log_type notice
log_type information
log_type debug

# Structured logging
log_format json
log_timestamp_format %Y-%m-%dT%H:%M:%S%z

# Connection logging
connection_messages true
log_clientid true
```

### Telegraf Pipeline Logging
```toml
# telegraf.conf
[agent]
  logfile = "/var/log/telegraf/telegraf.log"
  logfile_rotation_interval = "24h"
  logfile_rotation_max_size = "100MB"
  logfile_rotation_max_archives = 5

# MQTT Consumer logging
[[inputs.mqtt_consumer]]
  log = {
    level = "INFO"
    format = "json"
  }
```

### InfluxDB Logging
```yaml
# influxdb.conf
logging-level = "info"
log-with-id = true

# Structured JSON logging
log-format = "json"

# Log rotation
log-rotate-interval = "24h"
log-max-size = "100m"
log-max-archives = 5
```

---

## Voice Assistant Logging

### Audio Processing Logs
- **STT Events**: Speech recognition start/complete/fail
- **TTS Events**: Text-to-speech generation and playback
- **MCP Transactions**: Home Assistant command execution

### Performance Metrics
- **Response Times**: End-to-end processing latency
- **Audio Quality**: Signal-to-noise ratios, compression artifacts
- **Network Performance**: WebRTC connection stability

### Error Tracking
- **Connection Failures**: WebSocket disconnections, network issues
- **Processing Errors**: STT failures, LLM timeouts, TTS errors
- **MCP Failures**: Home Assistant communication issues

---

## Data Pipeline Observability

### Data Flow Monitoring
```python
def monitor_data_pipeline():
    """Monitor data flow health across all pipeline stages"""
    metrics = {
        "mqtt_messages_received": get_mqtt_message_count(),
        "telegraf_records_processed": get_telegraf_metric_count(),
        "influxdb_points_written": get_influxdb_write_count(),
        "grafana_queries_executed": get_grafana_query_count()
    }

    # Check for data flow issues
    if metrics["mqtt_messages_received"] > 0:
        if metrics["telegraf_records_processed"] == 0:
            log_error("Telegraf not processing MQTT messages")
        if metrics["influxdb_points_written"] == 0:
            log_error("InfluxDB not receiving data from Telegraf")

    return metrics
```

### Performance Metrics Logging
```python
def log_pipeline_performance():
    """Log key performance indicators"""
    perf_metrics = {
        "mqtt_ingestion_rate": calculate_ingestion_rate(),
        "telegraf_processing_latency": measure_processing_latency(),
        "influxdb_write_latency": measure_write_latency(),
        "data_freshness": measure_data_freshness(),
        "error_rate": calculate_error_rate()
    }

    logger.info("Pipeline performance metrics", extra={
        "metrics": perf_metrics,
        "alerts": generate_alerts(perf_metrics)
    })
```

---

## Error Handling and Alerting

### Error Classification
```python
ERROR_CATEGORIES = {
    "DATA_LOSS": {
        "patterns": ["write failed", "data dropped", "buffer overflow"],
        "severity": "CRITICAL",
        "alert": True
    },
    "CONNECTIVITY": {
        "patterns": ["connection lost", "broker unavailable", "network timeout"],
        "severity": "HIGH",
        "alert": True
    },
    "VALIDATION": {
        "patterns": ["invalid config", "schema mismatch", "field missing"],
        "severity": "MEDIUM",
        "alert": False
    },
    "PERFORMANCE": {
        "patterns": ["high latency", "slow processing", "resource exhaustion"],
        "severity": "MEDIUM",
        "alert": True
    }
}
```

### Alert Thresholds
```yaml
# Prometheus alerting rules
alerts:
  - name: "Data Ingestion Stopped"
    condition: "mqtt_messages_received == 0 for 5 minutes"
    severity: critical
    channels: [email, slack]

  - name: "High Processing Latency"
    condition: "telegraf_processing_latency > 30 seconds"
    severity: warning
    channels: [slack]
```

---

## Centralized Logging Setup

### Loki + Promtail Configuration
```yaml
# docker-compose.yml (logging stack)
version: '3.8'
services:
  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"

  promtail:
    image: grafana/promtail:latest
    volumes:
      - ./logs:/var/log
    command:
      - -config.file=/etc/promtail/config.yml
```

---

## Best Practices

### Log Message Standards
- **Structured Data**: Include relevant context (device_id, timestamps, metrics)
- **Consistent Naming**: Use standard field names across services
- **Trace IDs**: Include correlation IDs for request tracing
- **Avoid Sensitive Data**: Never log passwords, tokens, or personal information

### Voice Assistant Logging Standards
- **Audio Session Tracking**: Unique IDs for each voice interaction
- **Performance Metrics**: STT confidence scores, response times
- **Error Context**: Include audio format, network conditions, device info
- **Privacy Compliance**: No audio content logging, only metadata

### Monitoring Checklist
- [ ] All services logging to structured format (JSON)
- [ ] Log aggregation system configured
- [ ] Alert thresholds defined and tested
- [ ] Dashboard metrics validated
- [ ] Log retention policies implemented
- [ ] Regular log analysis performed
- [ ] Incident response procedures documented