---
description: Meta-rules for maintaining and improving IoT backend documentation and standards
alwaysApply: false
---

# IoT Backend Self-Improvement Rules

These meta-rules instruct AI agents to continuously maintain and improve project documentation, coding standards, and architectural records for the IoT backend repository.

---

## Core Principle

**Documentation is code.** Keep rules and decisions in sync with the codebase. Outdated documentation is worse than no documentation.

---

## When to Update Rules

### After Refactoring
- [ ] Did you establish a new pattern? → Add to `00-iot-backend-core/RULE.md`
- [ ] Did you make an architectural decision? → Add ADR to `../voice_assistant/docs/architecture/adr/` and update cross-repo rules
- [ ] Did you deprecate an approach? → Mark as deprecated with reason

### After Bug Fixes
- [ ] Did the bug reveal a missing guideline? → Add the guideline
- [ ] Was there a common mistake pattern? → Add to "avoid" list
- [ ] Did you learn something about external services? → Add to Learnings section

### After Adding Features
- [ ] **New service added?** → Update `docker-compose.yml` and `00-iot-backend-core/RULE.md`
- [ ] **New environment variable?** → Document in `env.example.txt` and `01-security-core/RULE.md`
- [ ] **New configuration option?** → Document in relevant config files and rules
- [ ] **Modified data pipeline?** → Update `10-data-schema/RULE.md` and `05-logging-standards/RULE.md`
- [ ] **Added monitoring/metrics?** → Document in Prometheus configuration and `05-logging-standards/RULE.md`
- [ ] Did you learn something about Docker networking? → Add to `00-iot-backend-core/RULE.md`
- [ ] **Changed deployment workflow?** → Update `docker-compose.yml` patterns and `00-iot-backend-core/RULE.md`

### After Code Review / Discussion
- [ ] Did you clarify a decision? → Add ADR if significant
- [ ] Did you answer "why did we do X?" → Document the answer

---

## What to Update

### `00-iot-backend-core/RULE.md` - Core Standards
Update when:
- New coding patterns are established
- Infrastructure patterns evolve
- Testing patterns are refined
- Error handling patterns are improved
- New tooling is configured

### ADR References
Add new ADR when:
- Making a choice between multiple valid approaches
- Establishing project-wide conventions
- Choosing external services or libraries
- Defining module boundaries
- Changing existing architecture
- Remember to update ADR index in `../voice_assistant/.cursor/rules/90-adr-index.mdc`

### This file (`80-self-improvement/RULE.md`)
Update when:
- The self-improvement process itself needs refinement
- New trigger conditions are identified
- Better documentation practices are discovered

---

## How to Document

### For Coding Standards
```markdown
## Section Name
- **Do this**: Explanation with example
- **Avoid this**: Why it's problematic
```

### For ADRs
Use the template in `../voice_assistant/docs/architecture/adr/README.md`:
- Context: What problem were we solving?
- Decision: What did we choose?
- Rationale: Why this choice?
- Consequences: What changed as a result?

### For Lessons Learned
```markdown
## Learnings
- **Issue**: What went wrong or was surprising
- **Solution**: How we fixed or handled it
- **Prevention**: How to avoid in future
```

---

## Self-Reflection Prompts

After completing a task, ask:

1. **Pattern Recognition**
   - "Did I repeat logic that should be centralized?"
   - "Did I follow an existing pattern, or create a new one?"

2. **Documentation Debt**
   - "Would another developer understand why I did this?"
   - "Is there a 'gotcha' that should be documented?"

3. **Rule Compliance**
   - "Did I follow the existing rules?"
   - "If I deviated, should the rule change or should my code?"

4. **Future Maintenance**
   - "What would I need to know to modify this later?"
   - "Are there assumptions that should be explicit?"

5. **Cross-Repository Impact**
   - "Does this change affect the voice_assistant repository?"
   - "Should cross-repository coordination be updated?"
   - "Does this affect shared infrastructure (ChromaDB, Prometheus, networking)?"

---

## Automation Hooks

### Testing Discipline
- Always run the appropriate test suite after completing code changes unless the user explicitly says not to. If you cannot run tests, state why and what to run (e.g., `.\.venv\Scripts\python.exe -m pytest` or a targeted file).

### Development Environment Awareness
- Always check if project uses Docker containers vs local development
- For containerized projects: Prefer `docker compose exec` for testing
- For local development: Use npm/node commands directly
- Document which services require rebuilds vs restarts
- Verify container networking for inter-service communication

### End of Refactoring Session
```
Before concluding, verify:
1. All new patterns documented in 00-iot-backend-core/RULE.md
2. Architectural decisions recorded as ADRs in voice_assistant/docs/architecture/adr/
3. Cross-repository coordination updated in 99-cross-repo/RULE.md
4. docker-compose.yml services synchronized with README.md
5. CHANGELOG.md updated with version changes
```

### End of Bug Fix
```
Before concluding, verify:
1. Root cause documented if non-obvious
2. Prevention guideline added if applicable
3. Related code patterns reviewed for same issue
```

---

## Rule Maintenance Standards

### Keep Rules DRY
- Don't duplicate guidance across files
- Cross-reference between rule files
- Use "See ADR-XXX" for detailed rationale

### Keep Rules Current
- Remove obsolete guidance immediately
- Mark deprecated patterns clearly
- Date significant changes

### Keep Rules Actionable
- Every rule should be verifiable
- Include examples (good and bad)
- Explain the "why" not just the "what"

---

## Cross-Repository Coordination

### Shared Infrastructure
- **ChromaDB**: Vector database for voice assistant RAG
- **Prometheus**: Unified monitoring across repositories
- **Networking**: Shared container networks
- **Environment Variables**: Consistent naming conventions

### Documentation Synchronization
- Changes to shared services require updates in both repositories
- ADR-022 governs voice assistant integration decisions
- Cross-repository rules must stay synchronized

### Communication Patterns
- Use `@-references` to link related rules across repositories
- Document inter-repository dependencies explicitly
- Maintain consistent terminology across repos

---

## File Organization

| File | Purpose | Update Frequency |
|---|---|---|
| `00-iot-backend-core/RULE.md` | Active coding standards | Every session with pattern changes |
| `../voice_assistant/docs/architecture/adr/*.md` | Design decisions with history | Major decisions only |
| `80-self-improvement/RULE.md` | Meta-rules for agents | Rarely, when process changes |
| `99-cross-repo/RULE.md` | Cross-repository coordination | When shared infrastructure changes |

---

## Example: Complete Update Cycle

**Scenario**: Refactored Docker networking for voice services

1. **Code change**: Updated `docker-compose.yml` with `voice-network`

2. **Rules update** (`00-iot-backend-core/RULE.md`):
   ```markdown
   ### Voice Assistant Integration
   - **Network Isolation**: Voice services communicate over dedicated `voice-network`
   ```

3. **ADR added** (`../voice_assistant/docs/architecture/adr/adr-022-iot-backend-integration.md`):
   ```markdown
   # ADR-022: IoT Backend Integration
   **Decision**: Voice assistant services deployed via iot-backend infrastructure
   **Rationale**: Unified deployment and monitoring
   ```

4. **Cross-repo update** (`99-cross-repo/RULE.md`): Added networking coordination guidelines

5. **Self-check**: "Is this documented well enough that the pattern won't regress?"
