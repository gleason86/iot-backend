# Cursor Agent Best Practices & AI Foundations

## Overview

This comprehensive guide documents best practices for Cursor agents, covering the `.cursor` directory structure, rules organization, command optimization, and the complete AI Foundations curriculum from [cursor.com/learn](https://cursor.com/learn).

## Table of Contents

1. [Cursor Agent Architecture](#cursor-agent-architecture)
2. [.cursor Directory Structure](#cursor-directory-structure)
3. [Rules Organization & Best Practices](#rules-organization--best-practices)
4. [Command Optimization](#command-optimization)
5. [Architecture Decision Records (ADRs)](#architecture-decision-records-adrs)
6. [Testing Standards](#testing-standards)
7. [AI Foundations Curriculum](#ai-foundations-curriculum)
8. [Self-Improvement Framework](#self-improvement-framework)
9. [Deployment & Development Workflow](#deployment--development-workflow)
10. [Optimizations & Key Insights](#optimizations--key-insights)

## Cursor Agent Architecture

### Core Components

- **Thin Client Architecture**: Clients connect to centralized Gateway for load-balanced AI processing
- **Primary Flow**: Client wake → Audio streaming → Gateway routing → Engine processing → Response streaming
- **Engine Processing**: STT (Whisper API) → LLM (ChatGPT API) with MCP tools → HA → TTS (Azure/OpenAI)

### Development Architecture

**Containerized Deployment (Primary):**
- All services run in Docker containers via `iot-backend/docker-compose.yml`
- Frontend served by Nginx container on port 3001
- Backend services auto-restart on code changes (Python hot reload)
- Assets built into container images during `docker compose build`

**Local Development (Secondary):**
- Frontend only: `cd voice_debug_ui; npm run dev` for hot reloading
- Backend only: Direct Python execution for debugging
- Not recommended for full-stack development due to networking complexity

**Deployment Workflow:**
1. Code changes → Commit to git
2. Container rebuild → `docker compose build <service>`
3. Service restart → `docker compose up -d <service>`
4. Test integration → Access via container ports

## .cursor Directory Structure

### Core Structure
```
.cursor/
├── commands/          # Executable commands (PowerShell scripts)
├── rules/            # Agent behavior rules (.mdc files)
├── plans/            # AI-generated project plans (optional)
├── debug.log         # Agent debugging logs
└── worktrees.json    # Git worktree configuration
```

### Rules File Format (.mdc)
```yaml
---
description: Brief description of rule purpose
globs: src/**/*.py, tests/**/*.py  # File patterns this applies to
alwaysApply: true/false           # Whether rule applies to all files
---

# Rule content in Markdown
```

### Commands Structure
- **test-\*.md** - Testing and validation
- **\*-\*.md** - Service management
- **\*-\*.md** - Health verification

## Rules Organization & Best Practices

### Numbering Convention
- `00-core.mdc` - Fundamental coding standards
- `01-testing.mdc` - Testing patterns and coverage
- `10-ha-integration.mdc` - Domain-specific rules (agent-requestable)
- `80-self-improvement.mdc` - Meta-rules for agents
- `90-adr-index.mdc` - Quick reference indexes

### Rule Types
- **alwaysApply: true** - Core standards that apply everywhere
- **alwaysApply: false** - Contextual rules (agent-requestable)
- **glob patterns** - Target specific file types/directories

### Key Rules Files

#### 00-core.mdc (Voice Assistant)
- Thin client architecture patterns
- Security & token management
- Development deployment workflows
- Project structure & imports
- Code organization standards
- Audio chain specifications
- Latency targets & monitoring

#### 01-testing.mdc
- Coverage targets: 85%+ overall (90% core logic, 70% integration)
- Test patterns and quality guidelines
- Mock external dependencies
- Integration test marking
- Coverage exclusions

#### 80-self-improvement.mdc
- Meta-rules for AI agents
- Self-reflection prompts
- Rule maintenance standards
- Documentation synchronization

#### 90-adr-index.mdc
- Quick reference to Architecture Decision Records
- Chronology validation (ADRs ≥ 2025-01-01)
- Decision categorization and cross-referencing

## Command Optimization

### PowerShell Best Practices
```powershell
# Use explicit venv paths (most reliable)
.\.venv\Scripts\python.exe -m pytest tests/

# Use ; for chaining (not &&)
cd project; pytest tests/

# Include usage examples and error handling
```

### Command Categories
- **test-\*.md** - Testing and validation
- **\*-\*.md** - Service management
- **\*-\*.md** - Health verification

### Example Commands

#### test-fast.md
```powershell
cd C:\Users\david\Repos\voice_assistant; .\.venv\Scripts\python.exe -m pytest tests/ -m "not integration" $args
```
- Quick pre-commit validation of unit tests
- Can target specific tests or files
- Requires `.venv` with dev dependencies

#### rebuild-changed.md
- Smart rebuild based on git changes
- Analyzes git diffs and rebuilds only affected services
- Provides time estimates and confirmation prompts

## Architecture Decision Records (ADRs)

### ADR Structure
- **Sequential numbering** but not necessarily chronological
- **Date validation** (>= repo creation date)
- **Template format** with Context/Decision/Rationale/Consequences
- **Cross-referencing** in index files

### ADR Categories
- **Core Architecture**: Entry points, package structure, modern packaging
- **Logging & Observability**: Config-based logging, observability patterns
- **Home Assistant Integration**: Area-aware resolution, MCP integration
- **LLM & Tool Execution**: Async modules, tool loops, parallel execution
- **Learning System**: Adaptive learning, confidence scoring, implicit feedback
- **Speech Processing**: STT backends, semantic endpointing, telemetry

### Key ADRs
- **ADR-001**: Diagnostic tools location
- **ADR-011**: Comprehensive logging system
- **ADR-012**: Area-aware entity resolution (40% area, 25% domain, 25% name, 10% keywords)
- **ADR-017**: Adaptive learning architecture
- **ADR-019**: Azure Speech integration (Python CLI mode)
- **ADR-021**: Voice input modes (Browser-based with Whisper API)

## Testing Standards

### Coverage Targets
- **85%+ overall** (90% core logic, 70% integration)
- **Exclude:** Hardware I/O, CLI, network calls, optional modules

### Test Organization
```python
class Test[Feature]:
    def test_[scenario]_[expected_result](self, fixture):
        """Test that [specific behavior]."""
        # Arrange → Act → Assert
```

### Quality Guidelines
1. **Descriptive names:** `test_<function>_<scenario>_<expected_result>`
2. **Mock external deps:** Mock HA, OpenAI, network calls, file I/O
3. **Test edge cases:** Empty inputs, None values, boundary conditions
4. **Test error handling:** Exceptions, validation failures, network errors
5. **One assertion focus:** Each test should verify one specific behavior
6. **Arrange-Act-Assert:** Clear test structure
7. **Use fixtures:** Share setup code via pytest fixtures in `conftest.py`

### Integration Test Marking
```python
@pytest.mark.integration  # Requires hardware/network
def test_audio_capture_from_microphone():
    pass
```

## AI Foundations Curriculum

### 1. How AI Models Work
**Core Concepts:**
- AI as API endpoints (non-deterministic results)
- Deterministic vs. probabilistic systems
- Token-based prediction from training data + user input
- Model trade-offs: intelligence vs. speed vs. cost
- Multiple modalities: text, images, voice, video

**Key Takeaway:** Never assume guaranteed identical responses.

### 2. Hallucination & Limitations
**Understanding Hallucinations:**
- AI confidently generates incorrect but plausible information
- Pattern-based prediction without "I don't know" capability
- Knowledge cutoff dates limit model awareness
- Common examples: fake APIs, incorrect imports, invalid configs

**Model Limitations:**
- Cannot generate truly random numbers
- Struggle with precise counting tasks
- Require verification mindset

**Best Practice:** "Verify in docs/codebase; provide error back to model"

### 3. Tokens & Pricing
**Token Fundamentals:**
- Smaller than words (e.g., "understanding" → "under", "stand", "ing")
- Pricing units: pay per token, not per word/character
- Input vs. output tokens (output costs 2-4x more)

**Economic Considerations:**
- Streaming enables real-time responses
- Be intentional about context size and response length
- Tokens measure both cost and speed (tokens per second)

### 4. Context
**Context Architecture:**
- Working memory maintaining conversation history
- System prompts defining model behavior/rules
- User messages and multi-modal inputs
- Automatic context inclusion (files, terminal output, errors)

**Context Management:**
- Context grows with each conversation turn
- Models have maximum context windows
- Compression and summarization techniques needed

### 5. Tool Calling
**Tool Calling Process:**
- AI models call external tools/APIs to extend capabilities
- JSON-formatted tool requests
- Results added back to conversation context

**Tool Components:**
- Name (e.g., `read_file`, `search_web`)
- Description (when/how to use)
- Parameters (required inputs)

**Coding Applications:**
- File read/write operations
- Code search and pattern matching
- Shell command execution
- Documentation and web access
- Error checking and testing

**Advanced Standards:**
- **MCP (Model Context Protocol)**: Universal AI-tool integration
- Cross-application tools (Figma, Linear, databases)

**Token Cost:** Tool definitions (input) + results (output)

### 6. Agents
**Agent Definition:** "Tools in a loop" - autonomous tool orchestration

**How Agents Work:**
- Goal-oriented task execution
- Autonomous planning and implementation
- Iterative self-checking and error correction
- GPS analogy: destination vs. turn-by-turn directions

**Role Transformation:**
- From task doer to task manager
- Parallel multi-agent workflows
- Human as architect/reviewer

**Agent Strengths:**
- Patterned refactoring across files
- Test addition for well-scoped errors
- Documentation updates
- Clear bug fixes with error messages

**Agent Limitations:**
- Complex system debugging
- Pixel-perfect visual design
- New/undocumented libraries
- Loop prevention (repeating failed approaches)
- High token consumption

**Guardrails:**
- Require passing tests before merging
- Human verification of changes
- Scope constraints to prevent unbounded modifications

**Delegation Strategy:**
- Start small with well-defined tasks
- Build confidence gradually
- Include checkpoints and verification

## Self-Improvement Framework

### Core Principle
**"Documentation is code"** - Keep rules and decisions synchronized with codebase. Outdated documentation is worse than no documentation.

### When to Update Rules
- **After Refactoring:** New patterns established
- **After Bug Fixes:** Missing guidelines revealed
- **After Adding Features:** New workflows or integrations
- **After Code Review:** Clarify architectural decisions

### Self-Reflection Prompts
After completing tasks, agents should ask:
1. **Pattern Recognition:** "Did I repeat logic that should be centralized?"
2. **Documentation Debt:** "Would another developer understand why I did this?"
3. **Rule Compliance:** "Did I follow existing rules?"
4. **Future Maintenance:** "What would I need to know to modify this later?"
5. **Deployment Impact:** "Does this affect containerized services or local development?"

### Rule Maintenance Standards
- **DRY Principles:** Don't duplicate guidance across files
- **Cross-Referencing:** Link between related rule files
- **Current Documentation:** Remove obsolete guidance immediately
- **Actionable Rules:** Every rule should be verifiable with examples

## Deployment & Development Workflow

### Container-First Architecture
- All services run in Docker containers
- Automatic rebuild/restart on code changes
- Hot reload for Python services
- Smart rebuild analysis based on git changes

### Environment Management
- `.env` for credentials (gitignored)
- Environment variables for all sensitive data
- Separate dev/prod configurations
- Container networking for inter-service communication

### Service Restart Guidelines
- **RESTART** (fast): Environment variables, config files, minor code changes
- **REBUILD** (slow): Dependencies, Dockerfiles, major architectural changes

### File Change Deployment Impact
| File Type | Location | Action |
|-----------|----------|--------|
| React/TSX/TS | `voice_debug_ui/src/` | `docker compose build voice-ui` |
| Python Code | `src/voice_poc/` | `docker compose restart voice-engine-*` |
| Config YAML | `config/*.yaml` | `docker compose restart <service>` |
| Environment | `.env` | `docker compose restart` |
| Dependencies | `pyproject.toml` | `docker compose build` |

## Optimizations & Key Insights

### Performance Optimizations
- **Debug Mode**: Runtime logs for complex bug debugging (2.2 release feature)
- **Cloud Agents**: Background processing without laptop dependency
- **Semantic Search**: 12.5% higher accuracy than regex-only search
- **A/B Testing**: Continuous validation of agent improvements
- **Productivity Impact**: 39% more PRs merged after agent adoption

### Development Efficiency
- **Rule-Based Guidance**: Structured .mdc files with glob patterns
- **Command Automation**: PowerShell scripts for common tasks
- **ADR Documentation**: Architectural decisions with rationale
- **Testing Discipline**: 85%+ coverage with clear quality standards
- **Self-Improving Agents**: Built-in reflection and documentation updates

### Agent Learning & Adaptation
- **Confidence Scoring**: Decision validation and improvement
- **Feedback Detection**: User corrections and implicit learning
- **Vector Storage**: Semantic search for similar commands
- **Multi-Agent Orchestration**: Parallel task execution

### Quality Assurance
- **Verification Mindset**: Every AI suggestion needs validation
- **Guardrails**: Prevent unbounded agent modifications
- **Human-in-the-Loop**: Critical decisions require oversight
- **Testing Integration**: Automated validation before merging

### Economic Considerations
- **Token Awareness**: Understand input/output token costs
- **Context Optimization**: Manage conversation length and relevance
- **Streaming Benefits**: Real-time responses without full completion waits
- **Tool Cost Awareness**: Additional tokens for tool definitions and results

## Key Mental Models

1. **Probabilistic Mindset**: Embrace non-deterministic AI responses
2. **Verification Discipline**: Every suggestion is a starting point, not final answer
3. **Economic Awareness**: Token costs drive optimization decisions
4. **Context Consciousness**: Memory limits shape conversation strategy
5. **Tool Integration**: AI as API orchestrator, not just text generator
6. **Delegation Wisdom**: Agent as fast junior developer requiring oversight
7. **Documentation Synchronization**: Rules must stay current with codebase

## Implementation Checklist

- [ ] Set up `.cursor` directory structure
- [ ] Create comprehensive rules files
- [ ] Implement command automation scripts
- [ ] Establish ADR documentation process
- [ ] Configure testing standards and coverage
- [ ] Enable self-improvement framework
- [ ] Optimize deployment workflows
- [ ] Train on AI foundations concepts

This comprehensive guide serves as the foundation for effective Cursor agent development and AI-assisted coding workflows.