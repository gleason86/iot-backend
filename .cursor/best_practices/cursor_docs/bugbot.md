# Bugbot - Automated Code Review System

## Overview

Bugbot is Cursor's automated code review system that analyzes pull requests to identify bugs, security vulnerabilities, and code quality issues. It integrates directly with GitHub and GitLab to provide intelligent, context-aware feedback on code changes.

**URL**: https://cursor.com/docs/bugbot
**Section**: Core
**Purpose**: Automated bug detection and code quality analysis

## How It Works

### Core Functionality
- **Automatic PR Analysis**: Reviews pull request diffs for issues
- **Security Scanning**: Identifies security vulnerabilities and unsafe patterns
- **Code Quality Checks**: Enforces coding standards and best practices
- **Context-Aware Feedback**: Uses project context and existing comments

### Review Triggers
- **Automatic**: Runs on every PR update
- **Manual**: Triggered by commenting `cursor review` or `bugbot run`
- **Draft Support**: Can review draft pull requests (configurable)

### Feedback Integration
- **Inline Comments**: Leaves specific comments on problematic code lines
- **Summary Comments**: Provides overall assessment and suggestions
- **Fix Links**: Direct links to fix issues in Cursor IDE or web interface
- **Context Preservation**: Reads existing PR comments to avoid duplication

## Setup Process

### Requirements
- **Cursor Plan**: Teams or Individual plan
- **GitHub/GitLab Access**: Admin access for repository integration
- **Organization Permissions**: GitHub org admin rights

### Installation Steps
1. **Connect Repository**:
   ```
   Go to cursor.com/dashboard → Integrations tab → Connect GitHub
   Follow GitHub installation flow
   ```

2. **Enable Bugbot**:
   ```
   Return to dashboard → Enable Bugbot on specific repositories
   Configure repository settings
   ```

3. **Configure Permissions**:
   ```
   Grant Cursor admin access
   Grant GitHub org admin access
   ```

## Configuration Options

### Repository Settings

#### Review Behavior
- **Run Frequency**: Once per PR vs. on every commit
- **Inline Reviews**: Enable/disable comments on specific code lines
- **Draft PR Support**: Include draft pull requests in automatic reviews

#### Access Control
- **Allow/Deny Lists**: Specify which users can trigger reviews
- **Team Requirements**: Configure team membership requirements
- **Manual Only**: Require explicit triggers instead of automatic reviews

### Personal Settings
**Override Options:**
- **Skip Reviews**: Disable Bugbot for personal PRs
- **Custom Rules**: Apply personal rule overrides
- **Notification Preferences**: Control review notification settings

### Project Context Files
**`.cursor/BUGBOT.md` Configuration:**
```
Project-specific rules and context for Bugbot reviews.
Supports nested files in subdirectories for scoped rules.
```

**File Hierarchy:**
```
project/
  .cursor/BUGBOT.md          # Always included (project-wide rules)
  backend/
    .cursor/BUGBOT.md        # Included when reviewing backend files
    api/
      .cursor/BUGBOT.md      # Included when reviewing API files
  frontend/
    .cursor/BUGBOT.md        # Included when reviewing frontend files
```

## Rules System

### Team Rules (Enterprise)
**Organization-wide Standards:**
- Created by team admins in Bugbot dashboard
- Automatically apply to all enabled repositories
- Enforce organization-wide coding standards
- Support for compliance and security requirements

### Rule Precedence
**Application Order:**
1. **Team Rules** (highest priority)
2. **Project BUGBOT.md** (including nested files)
3. **User Rules** (lowest priority)

### Rule Examples

#### Security Rules
```
Flag any use of eval() or exec()
Prevent dynamic code execution vulnerabilities
Require input sanitization for user data
```

#### License Compliance
```
Prevent importing disallowed OSS licenses
Check dependency license compatibility
Flag GPL license usage in commercial projects
```

#### Language Standards
```
Flag deprecated React patterns (componentWillMount)
Enforce TypeScript strict mode
Require proper error handling
```

#### Code Quality Standards
```
Require tests for backend changes
Enforce code coverage minimums
Check for TODO comments in production code
```

## Admin Configuration API

### API Key Creation
```
Cursor Dashboard → Settings tab → Advanced → New Admin API Key
Save the generated API key securely
```

### Repository Management
**Enable/Disable Endpoint:**
```bash
curl -X POST https://api.cursor.com/bugbot/repo/update \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "repoUrl": "https://github.com/your-org/your-repo",
    "enabled": true
  }'
```

**Parameters:**
- `repoUrl` (string, required): Full repository URL
- `enabled` (boolean, required): true to enable, false to disable

### API Response Handling
- **Caching**: Dashboard may take time to reflect API changes
- **State Verification**: API response shows current database state
- **Error Handling**: Check response codes for operation status

## Pricing Model

### Free Tier
**Included with Plans:**
- **Teams**: Limited reviews per team member per month
- **Individual**: Limited reviews per user per month
- **Reset**: Monthly billing cycle reset
- **Upgrade Path**: 14-day Pro trial available

### Pro Tier
**Unlimited Reviews:**
- **Cost**: $40 per user per month
- **Billing**: Per-user based on PR authorship
- **Seat Management**: Automatic license allocation
- **Seat Limits**: Configurable maximum seats per team

### Billing Mechanics
- **User Counting**: Based on PR authors reviewed by Bugbot
- **License Pooling**: Seats can be reassigned if unused
- **Cost Control**: Team admins can set seat limits
- **Billing Cycle**: Monthly with automatic seat management

### Abuse Prevention
**Guardrails:**
- **Pooled Cap**: 200 PRs per license per month
- **Scaling Support**: Contact for higher limits
- **Fair Usage**: Prevents system abuse while allowing legitimate use

## Analytics and Reporting

### Review Metrics
- **Detection Rate**: Bugs found per PR
- **Response Time**: Time to complete reviews
- **False Positives**: Accuracy of issue detection
- **Fix Adoption**: Percentage of suggested fixes applied

### Dashboard Features
- **Repository Overview**: Review status across all repos
- **Trend Analysis**: Bug detection trends over time
- **Team Performance**: Review quality by team member
- **Rule Effectiveness**: Which rules catch the most issues

## Troubleshooting

### Common Issues

#### Permission Problems
- **GitHub Access**: Verify app installation and repository permissions
- **Organization Admin**: Ensure org admin rights for setup
- **Repository Access**: Check Bugbot has read/write access

#### Configuration Issues
- **Rule Conflicts**: Check for conflicting team and project rules
- **File Paths**: Verify BUGBOT.md file locations and syntax
- **API Keys**: Confirm admin API key validity and permissions

#### Performance Issues
- **Review Delays**: Check system load and queue status
- **False Positives**: Adjust rule sensitivity and context
- **Missing Reviews**: Verify webhook configuration

### Diagnostic Tools
**Verbose Mode:**
```bash
# Enable detailed logging
Comment: cursor review verbose=true
Comment: bugbot run verbose=true
```

**Request IDs:**
- Include request IDs when reporting issues
- Available in verbose mode output
- Helps Cursor support diagnose problems

## FAQ

### Integration Questions
**"Does Bugbot read GitHub PR comments?"**
- Yes, Bugbot reads all PR comments (top-level and inline)
- Uses existing feedback to avoid duplicates
- Builds on previous reviewer suggestions

### Privacy and Security
**"Is Bugbot privacy-mode compliant?"**
- Respects Cursor privacy mode settings
- No data collection when privacy mode enabled
- Local processing for sensitive repositories

### Limits and Usage
**"What happens when I hit the free tier limit?"**
- Reviews pause until next billing cycle
- Existing reviews remain functional
- Upgrade available for unlimited access

### Enterprise Integration
**"How do I give Bugbot access to GitLab/GitHub Enterprise?"**
- Custom webhook configuration required
- Contact Cursor support for enterprise setup
- Additional security and compliance considerations

## Advanced Usage

### Custom Rule Development
1. **Identify Patterns**: Analyze common issues in your codebase
2. **Rule Creation**: Write specific detection rules
3. **Testing**: Validate rules against existing PRs
4. **Deployment**: Roll out via team rules or project files

### CI/CD Integration
1. **Webhook Setup**: Configure repository webhooks
2. **Status Checks**: Integrate with branch protection rules
3. **Automated Actions**: Trigger follow-up processes on review completion

### Compliance Workflows
1. **Security Standards**: Implement organization security policies
2. **Audit Trails**: Maintain review history for compliance
3. **Reporting**: Generate compliance reports from analytics

## Best Practices

### Rule Management
- **Start Simple**: Begin with basic security and quality rules
- **Iterate**: Refine rules based on false positives and missed issues
- **Document**: Maintain clear documentation for custom rules
- **Review**: Regularly audit rule effectiveness and relevance

### Team Adoption
- **Pilot Program**: Test Bugbot on selected repositories first
- **Training**: Educate team on interpreting Bugbot feedback
- **Feedback Loop**: Incorporate developer feedback for rule improvement

### Performance Optimization
- **Selective Application**: Use repository-specific rules when appropriate
- **Rule Tuning**: Adjust rule sensitivity to reduce noise
- **Caching**: Leverage snapshot and caching features

This comprehensive automated review system transforms code quality assurance, catching issues early in the development process while providing actionable feedback to developers.