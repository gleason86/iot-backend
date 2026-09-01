---
description: Cross-repository coordination and inter-dependencies for IoT backend and voice assistant
alwaysApply: false
---

# Cross-Repository Coordination Rules

This document governs coordination between the `iot-backend` and `voice_assistant` repositories, ensuring consistent patterns and preventing drift between shared infrastructure and documentation.

---

## Repository Overview

| Repository | Purpose | Primary Infrastructure |
|------------|---------|----------------------|
| `iot-backend` | IoT data pipeline and monitoring | MQTT → Telegraf → InfluxDB → Grafana |
| `voice_assistant` | Voice processing and HA control | STT → LLM → TTS with MCP integration |

---

## Shared Infrastructure Components

### Container Networks
- **iot-network**: IoT services (MQTT, Telegraf, InfluxDB, Grafana)
- **voice-network**: Voice services (Gateway, Engines, UI)
- **Coordination**: Changes to network configuration require updates in both repositories

### Shared Services
- **ChromaDB**: Vector database for RAG (managed by iot-backend, used by voice_assistant)
- **Prometheus**: Metrics collection (monitors both IoT and voice services)
- **Coordination**: Service configuration changes require cross-repository review

### Environment Variables
- **Naming Convention**: Consistent patterns across repositories
- **Documentation**: Variables documented in respective `env.example.txt` files
- **Coordination**: New shared variables require updates in both repos

---

## Inter-Repository Dependencies

### Data Flow Dependencies
```
Arduino Devices → iot-backend (MQTT) → voice_assistant (HA control)
                                      ↓
                               Shared Monitoring (Prometheus)
                                      ↓
                               Shared Vector Store (ChromaDB)
```

### Configuration Dependencies
- Voice assistant uses HA API tokens (managed in iot-backend environment)
- IoT backend provides ChromaDB for voice assistant RAG
- Both repositories share Prometheus monitoring infrastructure

---

## Rule Overlap Analysis

### Duplicate Rules (Avoid)
- **Security patterns**: Defined once in `01-security-core/RULE.md` (iot-backend)
- **Logging standards**: Defined once in `05-logging-standards/RULE.md` (iot-backend)
- **Cross-references**: Use `@` mentions to reference rules in other repositories

### Repository-Specific Rules
- **IoT Backend**: Docker orchestration, data pipeline patterns
- **Voice Assistant**: Voice processing, MCP integration patterns
- **Shared**: Security, logging, cross-repo coordination

---

## Cross-Reference Guidelines

### Rule References
```markdown
## Related Rules Files:
- `../voice_assistant/.cursor/rules/00-core/RULE.md` - Voice assistant development patterns
- `../voice_assistant/docs/architecture/adr/adr-022-iot-backend-integration.md` - Integration ADR
```

### ADR References
- ADR-022: IoT Backend Integration (primary coordination document)
- All shared infrastructure changes documented in voice_assistant ADRs
- Cross-repository impact assessed for each ADR

---

## Documentation Synchronization

### Required Updates for Shared Changes

#### When Adding New Shared Service
1. **iot-backend**: Update `docker-compose.yml`, `README.md`, `00-iot-backend-core/RULE.md`
2. **voice_assistant**: Update configuration files, documentation
3. **Cross-repo**: Update `99-cross-repo/RULE.md` with new dependency
4. **ADR**: Create ADR in voice_assistant for architectural decision

#### When Modifying Shared Network
1. **Both repos**: Update respective docker-compose.yml files
2. **Documentation**: Update network diagrams in both README.md files
3. **Rules**: Update network patterns in core rules
4. **Testing**: Verify inter-service communication

#### When Adding Shared Environment Variable
1. **Both repos**: Add to respective `env.example.txt` files
2. **Security**: Document in security rules if sensitive
3. **Validation**: Update configuration validation scripts

---

## Workspace-Level Coordination

### Cursor Rules Organization
```
.cursor/
├── rules/                          # Repository-specific rules
│   ├── 00-iot-backend-core/        # Core IoT patterns
│   ├── 01-security-core/           # Security standards
│   ├── 04-testing-standards/       # Testing patterns
│   ├── 05-logging-standards/       # Logging standards
│   ├── 10-data-schema/             # Data schema rules
│   ├── 20-error-handling/          # Error handling patterns
│   ├── 80-self-improvement/        # Self-maintenance rules
│   └── 99-cross-repo/              # Cross-repository coordination
├── commands/                       # Repository-specific commands
│   ├── stack-up.md                 # Full stack deployment
│   ├── validate-docs.md            # Documentation validation
│   └── voice-health.md             # Voice service monitoring
└── best_practices/                 # Optional advanced patterns
    ├── cursor_docs/                # Cursor system documentation
    └── agent-overview.md           # Agent capabilities
```

### Command Synchronization
- **Repository-specific**: Commands that only affect one repository
- **Shared infrastructure**: Commands that affect both (coordinate naming)
- **Cross-repository calls**: Commands can reference other repository paths

---

## Version Coordination

### Semantic Versioning Alignment
- Major versions: Breaking changes to shared interfaces
- Minor versions: New features, backward compatible
- Patch versions: Bug fixes, internal improvements

### Release Coordination
- **Staged releases**: iot-backend first, then voice_assistant
- **Rollback procedures**: Documented for shared infrastructure
- **Testing**: Cross-repository integration tests before releases

---

## Troubleshooting Guide

### Common Issues
- **Rule not applying**: Check glob patterns and `alwaysApply` settings
- **Cross-repo confusion**: Use ADR-022 as single source of truth
- **Documentation drift**: Run validation scripts in both repositories
- **Network connectivity**: Verify shared networks in docker-compose.yml

### Getting Help
- Check ADR-022 for integration decisions
- Review voice_assistant core rules for development patterns
- Run iot-backend documentation validation script
- Check cross-repository command outputs

---

## Maintenance Cadence

### Weekly
- Run documentation validation scripts
- Check for rule consistency across repositories
- Review shared infrastructure health

### Monthly
- Audit rule overlap and cross-references
- Verify ADR implementations match current architecture
- Update dependency documentation

### Quarterly
- Full cross-repository rule audit
- ADR relevance review
- Shared infrastructure performance review

---

## Quality Gates

### Pre-Commit Checks
- [ ] Documentation validation passes in both repositories
- [ ] Cross-repository references are valid
- [ ] Shared environment variables documented
- [ ] Network connectivity verified

### Release Gates
- [ ] Cross-repository integration tests pass
- [ ] Shared infrastructure documented
- [ ] ADR-022 updated for architectural changes
- [ ] Version numbers aligned between repositories

---

## Future Evolution

### Planned Improvements
- Automated cross-repository validation scripts
- Unified deployment workflows
- Shared infrastructure monitoring dashboards
- Automated ADR synchronization

### Deprecation Strategy
- Mark deprecated shared patterns in both repositories
- Maintain backward compatibility during transitions
- Document migration paths clearly

---

## Emergency Procedures

### Infrastructure Failure
1. **Isolate affected repository** to prevent cascade failures
2. **Check shared services** (ChromaDB, Prometheus) health
3. **Coordinate rollback** with other repository maintainers
4. **Update cross-repository documentation** post-recovery

### Rule Conflicts
1. **Identify conflict source** (which repository changed first)
2. **Review ADR-022** for coordination guidelines
3. **Update both repositories** to maintain consistency
4. **Document resolution** in cross-repo rules