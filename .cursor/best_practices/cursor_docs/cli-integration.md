# CLI Integration - Complete Reference

## Overview

Cursor CLI provides terminal-based access to AI agents, enabling developers to interact with AI assistance directly from the command line. Supports both interactive conversational sessions and non-interactive automation for CI/CD pipelines.

**URL**: https://cursor.com/docs/cli/overview
**Section**: Core
**Related Pages**: Installation, Using Agent, Shell Mode, MCP, Headless, Reference

## Core Features

### Dual Operation Modes

#### Interactive Mode
**Conversational Sessions:**
- Real-time dialogue with AI agents
- Review and approve proposed changes
- Maintain context across interactions
- Terminal-based code editing and execution

```bash
# Start interactive session
cursor-agent

# Start with initial prompt
cursor-agent "refactor the auth module to use JWT tokens"
```

#### Non-Interactive Mode
**Automation Support:**
- Script and CI/CD pipeline integration
- Print-based output for automation
- Model selection and output formatting
- Git change integration for reviews

```bash
# Run with specific prompt and model
cursor-agent -p "find and fix performance issues" --model "gpt-5"

# Use with git changes for review
cursor-agent -p "review these changes for security issues" --output-format text
```

### Session Management
**Conversation Persistence:**
- Resume previous conversations
- Maintain context across terminal sessions
- List and manage chat history
- Persistent conversation state

```bash
# List all previous chats
cursor-agent ls

# Resume latest conversation
cursor-agent resume

# Resume specific conversation
cursor-agent --resume="chat-id-here"
```

## Installation

### System Requirements
- **Operating System**: Linux, macOS, Windows (WSL)
- **Dependencies**: curl for installation script
- **Permissions**: User-level installation (no sudo required)

### Installation Process
```bash
# Download and install
curl https://cursor.com/install -fsS | bash

# Verify installation
cursor-agent --version
```

### Post-Installation Setup
- **Authentication**: Link to Cursor account
- **Configuration**: Set default preferences
- **Environment**: Configure shell environment variables

## Usage Patterns

### Development Workflows

#### Code Review and Analysis
```bash
# Review current branch changes
cursor-agent -p "review my recent changes for bugs"

# Analyze specific file
cursor-agent -p "analyze this file for performance issues" --file src/main.py

# Security audit
cursor-agent -p "check for security vulnerabilities"
```

#### Refactoring and Optimization
```bash
# Refactor function
cursor-agent "refactor this function to be more readable"

# Optimize performance
cursor-agent "optimize this code for better performance"

# Add error handling
cursor-agent "add proper error handling to this function"
```

#### Testing and Debugging
```bash
# Generate tests
cursor-agent "write unit tests for this function"

# Debug issue
cursor-agent "help me debug this error"

# Code explanation
cursor-agent "explain what this code does"
```

### CI/CD Integration

#### Automated Code Review
```bash
# In CI pipeline
cursor-agent -p "review PR for code quality issues" --output-format json

# Security scanning
cursor-agent -p "scan for security vulnerabilities" --exit-code
```

#### Automated Fixes
```bash
# Apply linting fixes
cursor-agent -p "fix all linting errors" --apply-changes

# Update dependencies
cursor-agent "update outdated dependencies"
```

## Advanced Features

### Shell Mode
**Enhanced Terminal Integration:**
- Direct command execution approval
- Interactive terminal sessions
- Real-time code modification
- Multi-step task execution

### MCP Integration
**Model Context Protocol Support:**
- Standardized tool integration
- External service connections
- Custom agent capabilities
- Protocol-compliant extensions

### Headless Operation
**Background Processing:**
- Non-interactive agent execution
- Server-side processing
- API-based integration
- Scalable automation

## Configuration Options

### Command-Line Flags

| Flag | Description | Example |
|------|-------------|---------|
| `-p, --prompt` | Specify initial prompt | `-p "review code"` |
| `--model` | Select AI model | `--model gpt-4` |
| `--output-format` | Output format (text/json) | `--output-format json` |
| `--resume` | Resume specific session | `--resume chat-123` |
| `--file` | Focus on specific file | `--file src/main.py` |
| `--apply-changes` | Auto-apply suggestions | `--apply-changes` |
| `--exit-code` | Return error codes | `--exit-code` |

### Environment Variables
```bash
# Set default model
export CURSOR_DEFAULT_MODEL="gpt-4"

# Configure output preferences
export CURSOR_OUTPUT_FORMAT="json"

# Set API endpoints
export CURSOR_API_URL="https://api.cursor.com"
```

### Configuration File
```json
{
  "defaultModel": "gpt-4",
  "outputFormat": "text",
  "autoApply": false,
  "maxTokens": 4096,
  "temperature": 0.7
}
```

## Integration Examples

### Git Workflow Integration
```bash
# Pre-commit hook
cursor-agent -p "run linting and fix issues" --apply-changes

# PR creation
cursor-agent -p "generate PR description" > pr-description.md
```

### Development Environment Setup
```bash
# Setup new project
cursor-agent "set up development environment for React app"

# Install dependencies
cursor-agent "install and configure all project dependencies"

# Configure tooling
cursor-agent "set up ESLint, Prettier, and testing framework"
```

### Documentation Generation
```bash
# Generate README
cursor-agent "create comprehensive README for this project"

# API documentation
cursor-agent "generate API documentation from code comments"

# Code comments
cursor-agent "add documentation comments to all public functions"
```

## Best Practices

### Interactive Mode Usage
- **Start Broad**: Begin with high-level goals
- **Iterate**: Refine requests based on agent responses
- **Review Changes**: Always review before applying
- **Context Preservation**: Use sessions for multi-step tasks

### Automation Guidelines
- **Idempotent Operations**: Design for safe re-runs
- **Error Handling**: Implement proper exit codes
- **Logging**: Enable verbose logging for debugging
- **Testing**: Test automation scripts thoroughly

### Security Considerations
- **Credential Management**: Never hardcode secrets
- **Permission Scope**: Limit agent permissions appropriately
- **Audit Logging**: Enable logging for compliance
- **Network Security**: Use secure connections for API calls

## Troubleshooting

### Common Issues

#### Installation Problems
- **Permission Denied**: Run installation as regular user
- **Path Issues**: Add Cursor CLI to system PATH
- **Dependency Conflicts**: Check for conflicting installations

#### Authentication Issues
- **Login Required**: Run `cursor-agent login` first
- **Token Expired**: Re-authenticate with `cursor-agent logout && cursor-agent login`
- **Permission Denied**: Check account permissions

#### Performance Issues
- **Slow Responses**: Check network connectivity
- **Memory Usage**: Monitor system resources
- **Rate Limiting**: Implement backoff strategies

### Diagnostic Commands
```bash
# Check installation
cursor-agent --version

# Test connectivity
cursor-agent --test-connection

# View logs
cursor-agent --logs

# Reset configuration
cursor-agent --reset-config
```

## Enterprise Integration

### Team Management
- **Shared Configurations**: Team-wide CLI settings
- **Usage Analytics**: Track CLI usage across team
- **Policy Enforcement**: Organization-wide rules and restrictions

### Compliance Features
- **Audit Logging**: Complete command and response logging
- **Data Residency**: Configurable data storage locations
- **Access Controls**: Role-based permissions for CLI usage

### Scaling Considerations
- **Concurrent Sessions**: Multiple simultaneous CLI sessions
- **Resource Management**: CPU and memory allocation
- **Queue Management**: Handle high-volume automation

## Future Developments

The CLI continues to evolve with:
- **Enhanced MCP Support**: More protocol integrations
- **Advanced Automation**: Complex workflow orchestration
- **Improved Performance**: Faster response times and processing
- **Extended Platform Support**: More operating systems and environments

This comprehensive CLI integration provides developers with powerful AI assistance directly in their preferred terminal environment, supporting everything from interactive development to full CI/CD automation.