---
description: Security best practices and secret management
globs: "**/*.{yml,yaml,env,conf}"
alwaysApply: true
---

# Security Rules

**CRITICAL**: Follow these rules to prevent credential exposure and security breaches.

---

## Rule 1: Never Hardcode Secrets

Never hardcode credentials, tokens, passwords, API keys, or other sensitive values directly in configuration files or code.

✅ **Good Example:**
```yaml
token: ${INFLUXDB_ADMIN_TOKEN}
password: ${MQTT_PASSWORD}
```

❌ **Bad Example:**
```yaml
# NEVER DO THIS
token: my-super-secret-token-12345
password: admin123
```

---

## Rule 2: Use Environment Variables

All sensitive values should come from environment variables:

| Pattern | Purpose |
|---------|---------|
| `${VARIABLE_NAME}` | YAML/Docker Compose syntax |
| `$VARIABLE_NAME` | Shell/Telegraf syntax |

### Environment Variable Naming Convention

```
SERVICE_ADMIN_USER      # Admin username
SERVICE_ADMIN_PASSWORD  # Admin password
SERVICE_ADMIN_TOKEN     # API token or auth token
SERVICE_HOST            # Service hostname
SERVICE_PORT            # Service port
```

---

## Rule 3: Provide Example Files

When a configuration file contains secrets:

1. **Gitignore the actual file** (e.g., `.env`, `password.txt`)
2. **Create a `.example` version** with placeholder values
3. **Document how to create** the actual file from the example
4. **Include comments** explaining each configuration option

**Pattern:**
| Actual File (gitignored) | Example File (committed) |
|--------------------------|--------------------------|
| `.env` | `env.example.txt` |
| `password.txt` | `password.txt.example` |
| `secrets.yaml` | `secrets.yaml.example` |

---

## Rule 4: Sensitive Data Patterns

Before committing, review files for these patterns:

| Pattern | Type |
|---------|------|
| `password`, `passwd` | Passwords |
| `token`, `secret`, `key` | Tokens/Keys |
| `api_key`, `apikey` | API Keys |
| `192.168.x.x`, `10.x.x.x` | Internal IPs |
| `@example.com` → should be fake | Email addresses |
| `://user:pass@` | Connection strings |

---

## Rule 5: Review Before Sharing

Before pushing to a public repository:

1. Run `git diff --cached` to review staged changes
2. Search for common secret patterns: `password`, `token`, `secret`, `key`, `credential`
3. Verify all `.env` and password files are gitignored
4. Check that no internal network information is exposed
5. Ensure example files only contain placeholder values

---

## Sensitive Files in This Project

| File | Status | Contains |
|------|--------|----------|
| `.env` | **Gitignored** | All service credentials |
| `mosquitto/password.txt` | **Gitignored** | MQTT user credentials (hashed) |
| `env.example.txt` | Committed | Template with placeholder values |
| `mosquitto/password.txt.example` | Committed | Instructions only |

---

## Docker-Specific Security

### Volume Permissions
```yaml
volumes:
  - ./config.conf:/etc/config.conf:ro  # Read-only mount
```

### Network Isolation
```yaml
networks:
  iot-network:
    driver: bridge
    internal: true  # For services that shouldn't have internet access
```

### Credential Injection
```yaml
environment:
  - MYSQL_PASSWORD=${MYSQL_PASSWORD}  # From .env file
secrets:
  - db_password  # Docker secrets (production)
```

---

## Voice Assistant Security Considerations

### API Key Management
- OpenAI API keys should be stored in `credentials/openai_api.yaml` (gitignored)
- Azure Speech credentials in `credentials/azure_speech.yaml` (gitignored)
- Home Assistant tokens in `credentials/ha_api.yaml` (gitignored)

### Container Security
- Voice services run in isolated containers
- WebRTC connections use secure protocols in production
- MCP server authentication required for Home Assistant access

### Network Security
- Voice services communicate over dedicated `voice-network`
- WebSocket connections should use WSS in production
- API endpoints should validate authentication tokens

---

## Security Validation Checklist

Before deployment:

- [ ] All secrets use environment variables, no hardcoded values
- [ ] `.env` file is gitignored and not committed
- [ ] Example files contain only placeholder values
- [ ] Docker volumes use read-only mounts where appropriate
- [ ] Network isolation configured for sensitive services
- [ ] Voice assistant credentials properly secured
- [ ] API keys validated and have appropriate permissions
- [ ] Home Assistant tokens have minimal required permissions

---

## Incident Response

### Credential Exposure
1. **Immediately rotate** all exposed credentials
2. **Audit access logs** for unauthorized usage
3. **Update deployment** with new credentials
4. **Review process** that led to exposure

### Security Breach
1. **Isolate affected systems** immediately
2. **Preserve evidence** for forensic analysis
3. **Notify stakeholders** according to incident response plan
4. **Implement fixes** and preventive measures
5. **Conduct post-mortem** to improve security processes