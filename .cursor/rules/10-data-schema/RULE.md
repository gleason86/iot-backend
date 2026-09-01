---
description: Canonical sensor data schema and field change procedures
globs: "telegraf/*.conf, grafana/**/*.json"
alwaysApply: false
---

# IoT Data Schema Standards

This document defines the canonical sensor data schema and procedures for schema changes.

---

## Canonical Schema Definition

The JSON payload from IoT devices:

```json
{
  "device_id": "string",           // Tag: Device identifier
  "temperature_c": "float",        // Field: Temperature in Celsius
  "temperature_f": "float",        // Field: Temperature in Fahrenheit
  "humidity": "float",             // Field: Relative humidity (%)
  "dew_point_c": "float",          // Field: Dew point in Celsius
  "dew_point_f": "float",          // Field: Dew point in Fahrenheit
  "motion": "boolean",             // Field: Motion detected flag
  "motion_count": "int",           // Field: Motion event count per interval
  "uptime_ms": "int",              // Field: Device uptime in milliseconds
  "temp_min_f": "float",           // Field: Session minimum temperature (F)
  "temp_max_f": "float",           // Field: Session maximum temperature (F)
  "humidity_min": "float",         // Field: Session minimum humidity
  "humidity_max": "float",         // Field: Session maximum humidity
  "status": "string",              // Field: Device status (online/offline)
  "ip": "string"                   // Field: Device IP address
}
```

---

## MQTT Topics

| Topic Pattern | Purpose |
|---------------|---------|
| `iot/sensors/{device_id}/data` | Sensor data payloads |
| `iot/sensors/{device_id}/status` | Device status updates |

---

## InfluxDB Schema

| Property | Value |
|----------|-------|
| **Measurement** | `sensor_data` |
| **Tags** | `device_id` |
| **Fields** | All sensor data fields listed above |

---

## Field Reference Table

| Field | Type | Description | Telegraf | Grafana Panel |
|-------|------|-------------|----------|---------------|
| device_id | string | Device identifier | Tag | Variable filter |
| temperature_f | float | Temperature (°F) | Field | Temperature chart, gauge |
| temperature_c | float | Temperature (°C) | Field | (available) |
| humidity | float | Relative humidity % | Field | Humidity chart, gauge |
| dew_point_f | float | Dew point (°F) | Field | Dew Point chart |
| dew_point_c | float | Dew point (°C) | Field | (available) |
| motion | boolean | Motion detected | Field | Motion Status stat |
| motion_count | int | Events per interval | Field | Motion Count bar chart |
| uptime_ms | int | Device uptime | Field | (available) |
| temp_min_f | float | Session min temp | Field | (available) |
| temp_max_f | float | Session max temp | Field | (available) |
| humidity_min | float | Session min humidity | Field | (available) |
| humidity_max | float | Session max humidity | Field | (available) |
| status | string | online/offline | Field | (available) |
| ip | string | Device IP | Field | (available) |

---

## Schema Change Procedures

### Adding a New Sensor Field

1. **Update Telegraf config** (`telegraf/telegraf.conf`):
   ```toml
   [[inputs.mqtt_consumer.json_v2.field]]
     path = "new_field_name"
     type = "float"  # or int, boolean, string
     optional = true
   ```

2. **Update Grafana dashboard** (`grafana/dashboards/iot-sensors.json`):
   - Add visualization panel(s) for the new field
   - Use `r._field == "new_field_name"` in Flux query
   - Choose correct unit type and visualization style

3. **Document the change** in `CHANGELOG.md`

4. **Restart services**:
   ```bash
   docker compose restart telegraf grafana
   ```

### Removing a Sensor Field

1. **Update Telegraf config**: Remove or comment out the field definition
2. **Update Grafana dashboards**: Remove any panels/queries referencing the field
3. **Note**: Historical data in InfluxDB will remain; no DB changes needed

### Renaming a Sensor Field

1. **Update Telegraf config**: Change the `path` value to match new field name
2. **Update all Grafana queries**: Search for old field name in dashboard JSON
3. **Consider migration**: Old data will use old field name; new data uses new name

---

## Voice Assistant Data Schema

### Audio Processing Schema
```json
{
  "session_id": "string",           // Unique voice session identifier
  "audio_format": "string",         // WAV, MP3, WebM, etc.
  "audio_duration_ms": "int",       // Audio clip duration
  "stt_provider": "string",         // openai, azure, etc.
  "stt_confidence": "float",        // 0.0 to 1.0 confidence score
  "stt_text": "string",             // Transcribed text
  "llm_model": "string",            // GPT model used
  "llm_tokens": "int",              // Token usage
  "response_text": "string",        // Generated response
  "tts_provider": "string",         // openai, azure, etc.
  "processing_time_ms": "int",      // Total end-to-end time
  "mcp_commands": "array",          // Home Assistant commands executed
  "error_type": "string"            // Error classification if failed
}
```

### Home Assistant Integration Schema
```json
{
  "command_type": "string",         // light, climate, media_player, etc.
  "entity_id": "string",            // homeassistant entity identifier
  "action": "string",               // turn_on, turn_off, set_temperature, etc.
  "parameters": "object",           // Action-specific parameters
  "success": "boolean",             // Command execution result
  "response_time_ms": "int",        // HA API response time
  "error_message": "string"         // Error details if failed
}
```

---

## Data Quality Standards

### Validation Rules
- **Device ID**: Must be unique, alphanumeric with hyphens/underscores
- **Temperature**: -50°C to 100°C (-58°F to 212°F) range validation
- **Humidity**: 0-100% range validation
- **Timestamps**: Must be valid ISO 8601 format
- **IP Addresses**: Must be valid IPv4 format when present

### Data Retention Policies
- **Raw sensor data**: 1 year retention
- **Aggregated data**: 5 year retention
- **Voice interaction logs**: 90 days retention (privacy compliance)
- **System metrics**: 1 year retention

---

## Schema Evolution Guidelines

### Backward Compatibility
- New fields must be optional in Telegraf configuration
- Grafana queries must handle missing fields gracefully
- API consumers must tolerate unknown fields

### Versioning Strategy
- Schema changes tracked in CHANGELOG.md
- Major changes require version bump
- Breaking changes require migration documentation

### Testing Schema Changes
- Unit tests for new field validation
- Integration tests for end-to-end data flow
- Grafana dashboard rendering tests
- Backward compatibility regression tests

---

## ADR References

- **ADR-022**: IoT Backend Integration (voice_assistant/docs/architecture/adr/)
  - Governs how voice data integrates with IoT schema
  - Defines separation between IoT sensor data and voice analytics

---

## Maintenance Checklist

After schema changes:
- [ ] Telegraf configuration updated with new fields
- [ ] Grafana dashboards updated with new queries
- [ ] CHANGELOG.md updated with schema changes
- [ ] Tests updated for new validation rules
- [ ] Documentation updated for new fields
- [ ] Cross-repository coordination completed
- [ ] Voice assistant schema compatibility verified