---
description: Testing standards for IoT data pipeline reliability and validation
globs: "**/*.{yml,yaml,conf,py,sh,ps1}"
alwaysApply: true
---

# IoT Testing Standards

> **Related Rules Files:**
> - `../00-iot-backend-core/RULE.md` - Project architecture and component locations
> - `../10-data-schema/RULE.md` - Data schema definitions and validation
> - `../20-error-handling/RULE.md` - Error handling and data loss prevention
> - `../80-self-improvement/RULE.md` - Testing maintenance guidelines

---

## Data Pipeline Testing Strategy

### Test Coverage Requirements
- **Critical Path**: 95%+ coverage for MQTT ingestion, Telegraf processing, InfluxDB storage
- **Integration Tests**: End-to-end data flow validation
- **Schema Validation**: All sensor data fields and types tested
- **Error Scenarios**: Network failures, malformed data, service restarts

### Testing Categories

#### 1. Unit Tests (`tests/unit/`)
```python
# Example: test_mqtt_parsing.py
def test_valid_sensor_payload():
    payload = {
        "device_id": "sensor_001",
        "temperature_f": 72.5,
        "humidity": 45.0
    }
    result = parse_mqtt_payload(payload)
    assert result["device_id"] == "sensor_001"
    assert result["temperature_f"] == 72.5
```

#### 2. Integration Tests (`tests/integration/`)
- **MQTT Broker Tests**: Publish/subscribe validation
- **Telegraf Pipeline Tests**: Configuration validation and data transformation
- **InfluxDB Tests**: Data persistence and query validation
- **Grafana Tests**: Dashboard rendering and query execution

#### 3. End-to-End Tests (`tests/e2e/`)
```bash
# Example: test_full_data_pipeline.sh
#!/bin/bash
# Publish test data to MQTT
mosquitto_pub -h localhost -t "iot/sensors/test/data" -m '{"device_id":"e2e_test","temperature_f":75.0}'

# Wait for processing
sleep 5

# Verify data in InfluxDB
influx query 'from(bucket:"iot") |> range(start:-1m) |> filter(fn: (r) => r.device_id == "e2e_test")'

# Verify dashboard accessibility
curl -f http://localhost:3000/d/iot-dashboard
```

---

## Test Environments

### Local Development Testing
```powershell
# Quick pipeline test
.\.cursor\commands\test-data-flow.ps1

# Full integration test suite
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

### Test Data Patterns
- **Synthetic Data**: Generate realistic sensor readings for testing
- **Edge Cases**: Min/max values, null fields, malformed JSON
- **Load Testing**: High-frequency data ingestion simulation
- **Failure Scenarios**: MQTT broker offline, InfluxDB full, network partitions

---

## Data Validation Testing

### Schema Compliance Tests
```python
def test_sensor_data_schema_compliance():
    """Ensure all sensor data matches canonical schema from 10-data-schema.mdc"""
    schema = load_canonical_schema()
    test_payloads = load_test_payloads()

    for payload in test_payloads:
        assert validate_payload(payload, schema), f"Schema violation: {payload}"
```

### Field Type Validation
```python
@pytest.mark.parametrize("field,expected_type,test_value", [
    ("temperature_f", float, 72.5),
    ("humidity", float, 45.0),
    ("motion", bool, True),
    ("device_id", str, "sensor_001"),
])
def test_field_types(field, expected_type, test_value):
    assert isinstance(test_value, expected_type), f"{field} should be {expected_type.__name__}"
```

---

## Voice Assistant Testing

### Audio Processing Tests
- **STT Accuracy**: Test speech-to-text conversion with various audio samples
- **TTS Quality**: Verify text-to-speech output meets quality standards
- **MCP Integration**: Test Home Assistant command execution

### Load Balancing Tests
- **Engine Distribution**: Verify requests are balanced across voice engines
- **Failover**: Test automatic switching when engines become unavailable
- **Performance**: Measure response times under various loads

### WebRTC Testing
- **Connection Stability**: Test WebSocket connections under network conditions
- **Audio Streaming**: Verify real-time audio transmission quality
- **Browser Compatibility**: Test across supported browsers

---

## Continuous Integration

### Pre-commit Hooks
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: validate-configs
        name: Validate Docker and Telegraf configs
        entry: python scripts/validate_configs.py
        language: system
        files: \.(yml|yaml|conf)$
        pass_filenames: false

      - id: test-data-flow
        name: Test data pipeline connectivity
        entry: ./.cursor/commands/test-data-flow.md
        language: system
        pass_filenames: false
```

### CI/CD Pipeline Requirements
- **Config Validation**: All YAML/JSON configs validated before deployment
- **Service Health Checks**: All containers must pass health checks
- **Data Flow Tests**: End-to-end data ingestion verified
- **Rollback Testing**: Ability to revert changes safely

---

## Quality Gates

### Code Quality
- **Linting**: All Python/YAML files pass linting checks
- **Type Hints**: Critical functions have type annotations
- **Documentation**: All public functions documented

### Deployment Readiness
- [ ] All tests pass (unit, integration, e2e)
- [ ] Configuration validated against schemas
- [ ] Service health checks pass
- [ ] Data pipeline verified end-to-end
- [ ] Rollback procedures tested
- [ ] Monitoring dashboards functional