---
description: Error handling patterns and data loss prevention strategies
globs: "**/*.{yml,yaml,conf,py,sh,ps1}"
alwaysApply: true
---

# IoT Error Handling & Data Loss Prevention

> **Related Rules Files:**
> - `../00-iot-backend-core/RULE.md` - Project architecture and infrastructure
> - `../04-testing-standards/RULE.md` - Testing standards for error scenarios
> - `../05-logging-standards/RULE.md` - Logging patterns for error tracking
> - `../80-self-improvement/RULE.md` - Error handling maintenance

---

## Error Classification Framework

### Criticality Levels
| Level | Impact | Response Time | Examples |
|-------|--------|---------------|----------|
| **CRITICAL** | Data loss, system down | Immediate (<5 min) | MQTT broker crash, InfluxDB corruption |
| **HIGH** | Service degradation | <15 minutes | High latency, partial data loss |
| **MEDIUM** | Functionality affected | <1 hour | Single device offline, dashboard errors |
| **LOW** | Minor inconvenience | <4 hours | Log warnings, cosmetic issues |

### Error Categories
```python
ERROR_CATEGORIES = {
    "DATA_LOSS": {
        "description": "Data cannot be stored or retrieved",
        "criticality": "CRITICAL",
        "recovery": "immediate_failover"
    },
    "CONNECTIVITY": {
        "description": "Network or service communication failures",
        "criticality": "HIGH",
        "recovery": "automatic_retry"
    },
    "VALIDATION": {
        "description": "Data format or schema violations",
        "criticality": "MEDIUM",
        "recovery": "graceful_degradation"
    },
    "RESOURCE": {
        "description": "Memory, disk, or CPU exhaustion",
        "criticality": "HIGH",
        "recovery": "load_shedding"
    },
    "CONFIGURATION": {
        "description": "Invalid or missing configuration",
        "criticality": "MEDIUM",
        "recovery": "fallback_config"
    }
}
```

---

## Data Loss Prevention Strategies

### 1. Message Persistence (MQTT)
```yaml
# docker-compose.yml - MQTT persistence
services:
  mosquitto:
    volumes:
      - mosquitto_data:/mosquitto/data
      - mosquitto_log:/mosquitto/log
    environment:
      - PERSISTENCE=true
      - PERSISTENCE_LOCATION=/mosquitto/data
      - AUTOSAVE_INTERVAL=30
```

### 2. Buffer Management (Telegraf)
```toml
# telegraf.conf - Buffer and retry settings
[agent]
  metric_batch_size = 1000
  metric_buffer_limit = 10000
  flush_interval = "10s"
  flush_jitter = "5s"

  # Output buffer settings
  [agent.output]
    buffer_limit = 10000
    buffer_when_full = "drop"  # Never drop - use "block" for guaranteed delivery

# InfluxDB output with retry
[[outputs.influxdb_v2]]
  urls = ["http://influxdb:8086"]
  token = "${INFLUXDB_TOKEN}"
  organization = "${INFLUXDB_ORG}"
  bucket = "${INFLUXDB_BUCKET}"

  # Retry configuration
  retry_on_http_error = true
  max_retry_attempts = 3
  retry_interval = "5s"
  exponential_backoff_base = 2
  exponential_backoff_max = "30s"
```

---

## Circuit Breaker Pattern

### Service Health Monitoring
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpenException("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
```

### Circuit Breaker Integration
```python
# InfluxDB operations with circuit breaker
influx_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

def write_to_influxdb(points):
    """Write data points with circuit breaker protection"""
    return influx_breaker.call(_write_to_influxdb_internal, points)
```

---

## Graceful Degradation Strategies

### Fallback Data Storage
```python
class FallbackStorage:
    def __init__(self, fallback_file="/tmp/iot_fallback.jsonl"):
        self.fallback_file = Path(fallback_file)
        self.max_file_size = 100 * 1024 * 1024  # 100MB

    def store_message(self, topic, payload):
        """Store message in fallback when InfluxDB is down"""
        if self._should_rotate_file():
            self._rotate_file()

        message = {
            "topic": topic,
            "payload": payload,
            "timestamp": datetime.now().isoformat(),
            "attempted_writes": 1
        }

        with open(self.fallback_file, 'a') as f:
            json.dump(message, f)
            f.write('\n')
```

### Service Degradation Levels
```python
SERVICE_DEGRADATION_LEVELS = {
    "NORMAL": {
        "description": "All services operational",
        "data_processing": "real_time",
        "retention": "full",
        "alerts": False
    },
    "DEGRADED": {
        "description": "Some services slow or partially unavailable",
        "data_processing": "buffered",
        "retention": "reduced",
        "alerts": True
    },
    "CRITICAL": {
        "description": "Core services failing",
        "data_processing": "fallback_only",
        "retention": "minimal",
        "alerts": True
    }
}
```

---

## Voice Assistant Error Handling

### Audio Processing Errors
- **STT Failures**: Fallback between providers (OpenAI → Azure)
- **Network Interruptions**: Resume interrupted audio streams
- **Quality Degradation**: Adaptive bitrate for poor connections

### MCP Error Handling
- **Home Assistant Unavailable**: Queue commands for retry
- **Entity Not Found**: Fuzzy matching with confidence scoring
- **Permission Denied**: Graceful failure with user notification

### WebRTC Error Recovery
- **Connection Loss**: Automatic reconnection with exponential backoff
- **Audio Stream Issues**: Fallback to alternative codecs
- **Browser Compatibility**: Feature detection and graceful degradation

---

## Recovery Procedures

### Automatic Recovery
```python
class AutoRecovery:
    def __init__(self):
        self.recovery_actions = {
            "mqtt_connection_lost": self._recover_mqtt_connection,
            "influxdb_write_failed": self._recover_influxdb_connection,
            "telegraf_config_invalid": self._reload_telegraf_config,
            "disk_space_low": self._cleanup_old_data
        }

    def execute_recovery(self, failure_type, context=None):
        if failure_type in self.recovery_actions:
            try:
                result = self.recovery_actions[failure_type](context)
                logger.info(f"Recovery successful: {failure_type}")
                return True
            except Exception as e:
                logger.error(f"Recovery failed: {failure_type}")
                return False
        return False
```

---

## Monitoring and Alerting

### Error Rate Monitoring
```yaml
# Prometheus alerting rules
groups:
  - name: iot_error_handling
    rules:
      - alert: HighErrorRate
        expr: rate(log_messages_total{level="error"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate > 10% for 5 minutes"

      - alert: CircuitBreakerOpen
        expr: circuit_breaker_state{state="open"} == 1
        for: 1m
        labels:
          severity: error
        annotations:
          summary: "Circuit breaker opened"
          description: "Service circuit breaker has opened due to failures"
```

---

## Testing Error Scenarios

### Chaos Engineering Tests
```python
def test_mqtt_broker_failure():
    """Test system behavior when MQTT broker fails"""
    stop_mqtt_broker()
    send_test_messages(10)
    assert check_dead_letter_queue() or check_retry_queue()
    start_mqtt_broker()
    assert verify_message_recovery()

def test_influxdb_write_failure():
    """Test behavior when InfluxDB write fails"""
    simulate_influxdb_failure()
    send_test_data_points(100)
    assert check_fallback_storage_populated()
    restore_influxdb()
    assert verify_data_replay()
```

---

## Best Practices Checklist

### Development
- [ ] All error paths have appropriate logging
- [ ] Circuit breakers implemented for external services
- [ ] Dead letter queues configured for unprocessable messages
- [ ] Fallback storage available for primary service failures
- [ ] Recovery procedures documented and tested

### Operations
- [ ] Alert thresholds configured for error rates
- [ ] Monitoring dashboards show error metrics
- [ ] Backup and recovery procedures tested regularly
- [ ] Incident response runbooks up to date
- [ ] Post-mortem reviews conducted for incidents

### Data Integrity
- [ ] Data validation at each pipeline stage
- [ ] Checksums or hashes for data integrity verification
- [ ] Audit logs for data modification tracking
- [ ] Backup verification procedures in place
- [ ] Data retention policies prevent accidental deletion