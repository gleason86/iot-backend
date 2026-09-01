# Agent System - Complete Reference

## Overview

Cursor's Agent system enables autonomous AI assistants that can execute complex, multi-step tasks across your codebase. Unlike traditional AI chat, agents can run commands, edit files, and work asynchronously in the background.

**Section**: Core
**Key Pages**: Cloud Agents, CLI, Inline Edit, Rules, Bugbot

## Agent Types

### 1. Local Agents (Foreground)
**Interactive agents** that run in your local Cursor instance with real-time collaboration.

**Access Methods:**
- **Chat Interface**: Agent dropdown in chat panel
- **Composer Mode**: Full-featured agent experience
- **Inline Agent**: Direct code editing with agent assistance

### 2. Cloud Agents (Background)
**Asynchronous agents** that run in isolated cloud environments, perfect for long-running tasks.

**Key Features:**
- **Isolated execution** in Ubuntu-based cloud VMs
- **Internet access** for package installation and API calls
- **Background processing** without tying up your local machine
- **Git integration** with automatic branch creation and PRs

## Cloud Agents Deep Dive

### Setup Process

#### UI Setup Flow (Recommended)
```bash
# Command Palette
Cmd+Shift+P → Cursor: Start Cloud Agent Setup
```

**Setup Steps:**
1. **Repository Connection**: Grant read-write access to GitHub/GitLab repos
2. **Environment Configuration**: Define base environment and dependencies
3. **Snapshot Creation**: Capture configured environment state for reuse
4. **Secret Management**: Configure API keys and environment variables

#### Manual Setup (Advanced)
For complex environments requiring custom Docker configurations:

```dockerfile
# .cursor/Dockerfile
FROM ubuntu:22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    python3 \
    git \
    curl

# Don't COPY project files - Cursor manages workspace
```

### Environment Configuration

#### environment.json Structure
```json
{
  "snapshot": "POPULATED_FROM_SETTINGS",
  "install": "npm install",
  "start": "sudo service docker start",
  "terminals": [
    {
      "name": "Run Next.js",
      "command": "npm run dev"
    }
  ]
}
```

#### Command Types
- **install**: Run when setting up new environment (caches disk state)
- **start**: Run when starting agent (for services like Docker)
- **terminals**: Commands that run in tmux sessions for agent access

### Secret Management

#### Secrets Tab (Recommended)
- **Location**: Cursor Settings → Cloud Agents → Secrets
- **Security**: Encrypted at rest using KMS
- **Scope**: Available as environment variables to all cloud agents
- **Management**: Shared across workspace/team

#### Monorepo Considerations
For projects with multiple `.env.local` files:
```bash
# Add all secrets with unique prefixes
NEXTJS_API_KEY=...
CONVEX_API_KEY=...
```

### Testing and Verification

#### Cloud Instance Testing
1. **SSH Access**: Click dropdown → "Open VM" in agent sidebar
2. **Port Forwarding**: Access web services running in cloud
3. **Interactive Testing**: Run commands, check logs, verify functionality

#### Local Testing
```bash
# Checkout agent branch
git fetch origin
git checkout <agent-branch-name>

# Set up environment
cp .env.local .  # or reference Cursor secrets
npm install

# Run tests
npm test
npm run dev
```

### CI/CD Integration

#### Branch Management
- Agents create feature branches automatically
- Push changes and create pull requests
- Standard Git workflow integration

#### Verification Workflows
- **Pre-merge testing** in cloud environment
- **Automated checks** before PR creation
- **Rollback support** via checkpoint system

## CLI Integration

### CLI Agent Features
**URL**: https://cursor.com/docs/cli/overview

#### Core Capabilities
- **Shell Mode**: Interactive terminal sessions with agent assistance
- **MCP Support**: Model Context Protocol integration
- **Headless Operation**: Background processing without UI
- **Reference Mode**: API-like access to agent functionality

#### Installation
```bash
# Install Cursor CLI
cursor install-cli

# Or via npm
npm install -g @cursor/cli
```

#### Usage Patterns
```bash
# Interactive shell mode
cursor shell

# Run agent with specific task
cursor agent "optimize this React component"

# MCP server integration
cursor mcp add-server my-server
```

## Inline Edit System

### Overview
**URL**: https://cursor.com/docs/inline-edit/overview

#### Key Features
- **Terminal Integration**: Edit files directly from terminal output
- **Live Preview**: See changes before applying
- **Context Preservation**: Maintains full codebase context
- **Multi-file Support**: Edit across multiple files simultaneously

#### Terminal Integration
```bash
# Edit from terminal output
cursor inline-edit file.js:10

# Edit with AI assistance
cursor inline-edit --ai "fix this bug"
```

## Rules System

### Project Rules
**URL**: https://cursor.com/docs/context/rules

#### Rule Architecture
- **Project-scoped**: `.cursor/rules/` directory
- **File patterns**: Apply to specific file types via globs
- **Multiple formats**: MDC (Markdown Cursor) files
- **Inheritance**: Local rules override team/global rules

#### Rule Structure
```mdc
---
description: Brief description of rule purpose
globs: src/**/*.py, tests/**/*.py
alwaysApply: true
---

# Rule content in Markdown
```

#### Rule Types
- **alwaysApply: true**: Core standards (imports, patterns)
- **alwaysApply: false**: Contextual rules (agent-requestable)
- **Team Rules**: Organization-wide standards
- **AGENTS.md**: Agent-specific guidance

#### Best Practices
- **DRY Principles**: Cross-reference related rules
- **Version Control**: Commit rules with codebase
- **Gradual Adoption**: Start with core standards
- **Documentation**: Update rules when patterns change

## Bugbot System

### Automated Bug Detection
**URL**: https://cursor.com/docs/bugbot

#### Capabilities
- **Static Analysis**: Identify potential bugs before runtime
- **Pattern Recognition**: Learn from common error patterns
- **Rule Integration**: Apply custom bug detection rules
- **Multi-language Support**: Works across different programming languages

#### Integration with Agents
- **Automatic Fixes**: Suggest and apply bug fixes
- **Rule-based Detection**: Custom rules for project-specific issues
- **Learning System**: Improves detection accuracy over time

## Agent Best Practices

### Task Delegation Strategy
1. **Start Small**: Begin with well-defined, low-risk tasks
2. **Build Confidence**: Gradually delegate larger work chunks
3. **Include Checkpoints**: Regular verification throughout process
4. **Human Oversight**: Critical decisions require review

### Agent Limitations Awareness
- **Complex Debugging**: Still requires human insight for systemic issues
- **Visual Design**: Pixel-perfect implementation needs human guidance
- **New Libraries**: May struggle with undocumented dependencies
- **Token Costs**: High consumption for complex multi-step tasks

### Workflow Optimization
1. **Parallel Processing**: Multiple agents for different tasks
2. **Background Execution**: Cloud agents for long-running work
3. **Checkpoint System**: Undo capability for agent changes
4. **Integration**: Combine with Tab, Rules, and other Cursor features

## Security Considerations

### Cloud Agent Security
- **Isolated VMs**: Each agent runs in separate environment
- **Git Permissions**: Read-write access only to specified repos
- **Internet Access**: Controlled for package installation
- **Data Exfiltration Protection**: Monitoring for malicious activities

### Privacy Controls
- **Privacy Mode**: Disable data collection during agent runs
- **Secret Management**: Encrypted storage and controlled access
- **Audit Logging**: Track agent actions and changes

## Performance Optimization

### Environment Setup
- **Snapshot Caching**: Reuse configured environments
- **Efficient Install Commands**: Design for multiple runs
- **Minimal Dependencies**: Only install required packages
- **Fast Startup**: Optimize start commands for quick initialization

### Cost Management
- **Token Awareness**: Monitor usage across agent sessions
- **Selective Execution**: Use cloud agents for expensive operations
- **Caching Strategies**: Reuse computed results when possible

## Troubleshooting

### Common Issues
- **Environment Setup**: Verify Docker configuration and dependencies
- **Secret Access**: Check Secrets tab configuration
- **Git Permissions**: Ensure proper repository access
- **Network Issues**: Verify internet connectivity for package installation

### Recovery Procedures
- **Failed Setup**: Re-run setup wizard or edit environment.json manually
- **Missing Secrets**: Add via Secrets tab or environment variables
- **Branch Conflicts**: Resolve merge conflicts before agent completion
- **Performance Issues**: Scale environment or optimize commands

## Future Developments

The agent system continues to evolve with:
- **Enhanced Multi-agent Coordination**
- **Improved Context Understanding**
- **Advanced Tool Integration**
- **Better Error Recovery**
- **Expanded Language Support**

This comprehensive agent system represents Cursor's vision for autonomous AI-assisted development, combining local intelligence with cloud-scale processing capabilities.