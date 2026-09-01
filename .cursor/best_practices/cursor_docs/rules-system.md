# Rules System - Complete Reference

## Overview

Cursor's Rules system provides persistent, reusable context for AI agents. Rules bundle prompts, scripts, and instructions together, ensuring consistent guidance across your team and codebase.

**URL**: https://cursor.com/docs/context/rules
**Section**: Context
**Purpose**: System-level instructions for Agent behavior

## Rule Types

### 1. Project Rules
**Location**: `.cursor/rules/` directory
**Scope**: Version-controlled, codebase-specific
**Application**: Manual, pattern-based, or intelligent selection

### 2. User Rules
**Location**: Cursor Settings → Rules
**Scope**: Global to your Cursor environment
**Application**: Used by Agent (Chat) across all projects

### 3. Team Rules
**Location**: Cursor Dashboard (Team/Enterprise plans)
**Scope**: Organization-wide
**Application**: Automatically applied to all team members

### 4. AGENTS.md
**Location**: Project root or subdirectories
**Scope**: Simple markdown instructions
**Application**: Plain markdown alternative to structured rules

## How Rules Work

### Core Mechanism
- **Persistent Context**: Rules provide reusable instructions that persist across chat sessions
- **Prompt Integration**: Rule contents are included at the start of model context
- **Memory Compensation**: Addresses LLM limitation of no memory between completions

### Application Methods
- **Always Apply**: Rule applied to every chat session
- **Apply Intelligently**: Agent decides relevance based on description
- **Apply to Specific Files**: Triggered by file pattern matching
- **Apply Manually**: Invoked via @-mentions (e.g., `@my-rule`)

## Project Rules Deep Dive

### Folder Structure
```
.cursor/rules/
├── my-rule/
│   ├── RULE.md           # Main rule file
│   └── scripts/          # Helper scripts (optional)
```

### Rule Anatomy

#### RULE.md File Format
```mdc
---
description: Brief description of rule purpose
globs: src/**/*.py, tests/**/*.py  # File patterns
alwaysApply: true                  # Application method
---

# Rule Content

## Guidelines
- Use our internal RPC pattern when defining services
- Always use snake_case for service names

## Examples
@service-template.ts
```

#### Frontmatter Properties
- **`description`**: Brief explanation for agent decision-making
- **`globs`**: File patterns that trigger rule application
- **`alwaysApply`**: Boolean for automatic application

### Creating Rules

#### Via Command Palette
```bash
# Command Palette
Cmd+Shift+P → New Cursor Rule
```

#### Via Settings
```
Cursor Settings → Rules, Commands → + Add Rule
```

### Rule Management
- **Status Monitoring**: View all rules and their status in settings
- **Draft Mode**: Save rules as drafts before enabling
- **Version Control**: Rules are committed with your codebase

## Best Practices

### Rule Design Principles
- **Focused Scope**: Keep rules under 500 lines
- **Composable**: Split large rules into multiple focused rules
- **Concrete Examples**: Include specific examples or referenced files
- **Clear Guidance**: Avoid vague instructions; write like internal documentation
- **Reusable**: Create rules for frequently repeated prompts

### Content Guidelines
- **Actionable Instructions**: Provide specific, implementable guidance
- **Context Awareness**: Include relevant codebase knowledge
- **Standardization**: Encode domain-specific knowledge and patterns
- **Workflow Automation**: Define project-specific processes

### Performance Considerations
- **Token Efficiency**: Rules consume context window space
- **Selective Application**: Use appropriate application methods
- **Regular Maintenance**: Review and update rules as patterns evolve

## Team Rules

### Enterprise Features
**Plans**: Team and Enterprise plans
**Management**: Cursor Dashboard administration
**Enforcement**: Optional mandatory application

### Management Workflow
1. **Admin Creation**: Create rules in Cursor Dashboard
2. **Team Distribution**: Automatically available to all team members
3. **Enforcement Options**: Optional mandatory application
4. **Visibility**: Rules visible in dashboard and individual settings

### Enforcement Levels
- **Optional**: Team members can disable (default)
- **Enforced**: Mandatory for all team members
- **Security Note**: AI guidance should complement, not replace, security controls

### Application Order
**Precedence Hierarchy:**
1. **Team Rules** (highest precedence)
2. **Project Rules**
3. **User Rules** (lowest precedence)

**Conflict Resolution**: Earlier sources take precedence when guidance conflicts

## AGENTS.md

### Simple Alternative
**Format**: Plain markdown file
**Location**: Project root or subdirectories
**Purpose**: Lightweight alternative to structured rules

### File Structure
```markdown
# Project Instructions

## Code Style
- Use TypeScript for all new files
- Prefer functional components in React
- Use snake_case for database columns

## Architecture
- Follow the repository pattern
- Keep business logic in service layers

## Communication Style
Please reply in a concise style. Avoid unnecessary repetition or filler language.
```

### Nested Support
- **Project Root**: Main AGENTS.md applies to entire project
- **Subdirectories**: Scoped AGENTS.md for specific areas
- **Inheritance**: Subdirectory rules can override or extend root rules

### Advantages
- **Simplicity**: No metadata or complex configurations
- **Readability**: Plain markdown format
- **Flexibility**: Easy to edit and maintain
- **Migration Path**: Simple transition from legacy formats

## User Rules

### Global Preferences
**Location**: Cursor Settings → Rules
**Scope**: Applied across all projects
**Purpose**: Personal coding preferences and communication style

### Common Use Cases
- **Communication Style**: Preferred response format and tone
- **Coding Conventions**: Personal naming and structure preferences
- **Workflow Preferences**: Default approaches to common tasks

### Configuration
```
Cursor Settings → Rules → User Rules section
```

## Importing Rules

### Remote Rules (GitHub)
- **Source**: Any accessible GitHub repository
- **Sync**: Automatic updates from remote source
- **Management**: Import via Cursor Settings → Rules

### Agent Skills
- **Standard**: Open standard for AI agent extensions
- **Import**: Automatic loading from compatible sources
- **Application**: Always treated as agent-decided rules
- **Control**: Toggle via Cursor Settings → Rules → Import Settings

## Legacy Support

### .cursorrules (Deprecated)
- **Status**: Still supported but deprecated
- **Migration**: Recommended to migrate to Project Rules or AGENTS.md
- **Location**: Project root

### .mdc Cursor Rules (Legacy)
- **Status**: Functional but legacy
- **New Rules**: All new rules created as folders in `.cursor/rules/`
- **Reason**: Improved readability and maintainability

## Examples

### Frontend Components Rule
```mdc
---
description: "Standards for frontend components and API validation"
alwaysApply: false
---

## Component Structure
- Use functional components with TypeScript
- Implement proper error boundaries
- Follow atomic design principles

## API Integration
- Use React Query for data fetching
- Implement proper loading and error states
- Validate API responses with Zod schemas
```

### Service Templates Rule
```mdc
---
description: "Templates for Express services and React components"
globs: src/**/*.ts, src/**/*.tsx
alwaysApply: false
---

## Express Services
- Use dependency injection pattern
- Implement proper error handling middleware
- Include comprehensive logging

## React Components
- Use custom hooks for business logic
- Implement proper TypeScript interfaces
- Follow accessibility guidelines
```

### Workflow Automation Rule
```mdc
---
description: "Automating development workflows and documentation generation"
alwaysApply: false
---

## Code Generation
- Use consistent naming conventions
- Generate comprehensive tests
- Include proper documentation comments

## Documentation
- Auto-generate API documentation
- Maintain changelog updates
- Generate deployment guides
```

## FAQ

### Rule Application Issues
**"Why isn't my rule being applied?"**
- Check `alwaysApply` setting
- Verify glob patterns match files
- Ensure rule is enabled in settings
- Check for conflicting team rules

### Rule References
**"Can rules reference other rules or files?"**
- Yes, rules can reference other files in the project
- Use relative paths for local references
- Include examples via file references

### Chat Integration
**"Can I create a rule from chat?"**
- Yes, use the "Create Rule" option in chat
- Agent can suggest rule creation from conversations
- Rules can be refined through iterative chat

### Feature Integration
**"Do rules impact Cursor Tab or other AI features?"**
- Rules primarily affect Agent (Chat)
- Tab learns independently but can benefit from rule guidance
- Inline Edit respects rule context when available

### Scope Questions
**"Do User Rules apply to Inline Edit?"**
- User Rules apply to Agent (Chat)
- Inline Edit has separate context handling
- Project rules may influence Inline Edit behavior

## Implementation Strategy

### Getting Started
1. **Assess Needs**: Identify repetitive patterns or standards
2. **Start Small**: Create focused rules for specific use cases
3. **Iterate**: Refine rules based on usage and feedback
4. **Scale**: Expand to team rules as organization grows

### Team Adoption
1. **Pilot Program**: Start with small team or project
2. **Standardization**: Establish core organizational rules
3. **Training**: Educate team on rule usage and creation
4. **Governance**: Define processes for rule creation and maintenance

### Maintenance Practices
1. **Regular Review**: Audit rules for relevance and accuracy
2. **Version Control**: Track rule changes with codebase
3. **Documentation**: Maintain rule documentation and examples
4. **Feedback Loop**: Incorporate team feedback for improvements

This comprehensive rules system enables teams to encode organizational knowledge, standardize practices, and enhance AI agent effectiveness across the entire development lifecycle.