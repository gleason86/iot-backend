# Inline Edit - Complete Reference

## Overview

Inline Edit provides direct code editing capabilities within the editor, allowing developers to modify code or ask questions using contextual AI assistance without leaving their current workflow.

**URL**: https://cursor.com/docs/inline-edit/overview
**Section**: Core
**Related Pages**: Terminal integration

## Core Functionality

### Access Methods
- **Keyboard Shortcut**: `Ctrl+K` (opens inline input field)
- **Selection-Based**: Works with or without code selection
- **Contextual**: Uses surrounding code for intelligent suggestions

### Edit Modes

#### 1. Edit Selection
**Targeted Code Modification:**
- Select specific code blocks
- Provide editing instructions
- AI modifies only the selected portion
- Precise, controlled changes

#### 2. Generate at Cursor
**Code Insertion:**
- No selection required
- AI generates code at cursor position
- Includes surrounding context automatically
- Function-aware (includes entire functions when triggered on function names)

#### 3. Quick Question
**Code Analysis:**
- Press `Alt+Enter` in inline editor
- Ask questions about selected code
- Get explanations and insights
- Convert answers to code with "do it" commands

### Advanced Features

#### Full File Edits
**Comprehensive Changes:**
- Use `Ctrl+Shift+Enter` for file-wide modifications
- Maintains control while allowing broad changes
- Preserves file structure and intent

#### Send to Chat
**Escalation Path:**
- Use `Ctrl+L` for complex multi-file scenarios
- Access full Chat capabilities
- Multi-file editing support
- Advanced AI features and explanations

## Workflow Integration

### Follow-up Instructions
**Iterative Refinement:**
- Add instructions after initial edits
- Press `Enter` to apply refinements
- AI updates based on feedback
- Progressive improvement of results

### Default Context
**Intelligent Context Inclusion:**
- Automatically includes related files
- Incorporates recently viewed code
- Adds relevant project information
- Prioritizes most relevant context for better results

## Terminal Integration

### Terminal-Based Editing
**Command-Line Access:**
- Edit files directly from terminal output
- Real-time code modification capabilities
- Seamless terminal-to-editor workflow
- Integrated development experience

## Best Practices

### When to Use Inline Edit
- **Quick fixes**: Small, targeted code changes
- **Code generation**: Adding new functionality at cursor
- **Understanding code**: Quick questions about complex logic
- **Iterative development**: Progressive refinement of changes

### When to Escalate to Chat
- **Multi-file changes**: Cross-file modifications needed
- **Complex logic**: In-depth analysis or major restructuring
- **Documentation**: Comprehensive code explanations
- **Advanced features**: Full AI capabilities required

### Efficiency Tips
- **Precise selections**: Select exactly what you want to change
- **Clear instructions**: Provide specific, actionable guidance
- **Iterative approach**: Use follow-up instructions for refinement
- **Context awareness**: Let Cursor include relevant surrounding code

## Integration with Other Features

### Tab System
- Inline Edit can apply Tab suggestions
- Complements Tab's predictive capabilities
- Different access patterns for different use cases

### Agent System
- Escalation path to full agent capabilities
- Chat integration for complex scenarios
- Unified AI assistance ecosystem

### Rules System
- Respects project and user rules
- Applies contextual guidelines
- Maintains consistency with established patterns

## Performance Considerations

### Response Times
- **Fast for small edits**: Quick local processing
- **Context-dependent**: Larger context may increase processing time
- **Network-dependent**: Requires internet for AI processing

### Resource Usage
- **Memory efficient**: Minimal local resource consumption
- **Context-aware**: Only processes relevant code sections
- **Scalable**: Handles files of various sizes appropriately

## Security and Privacy

### Code Handling
- **Local processing**: Code analysis happens securely
- **No permanent storage**: Code not retained after session
- **Privacy controls**: Respects Cursor privacy settings
- **Secure transmission**: Encrypted communication with AI services

## Troubleshooting

### Common Issues
- **No suggestions appearing**: Check internet connectivity
- **Context issues**: Ensure relevant files are accessible
- **Selection problems**: Verify code selection is valid
- **Performance lag**: Reduce context size or check network

### Recovery Steps
- **Restart**: Close and reopen inline editor
- **Clear context**: Use smaller selections
- **Check settings**: Verify AI features are enabled
- **Network test**: Confirm internet connectivity

This inline editing system provides developers with immediate AI assistance directly within their coding workflow, enabling rapid iteration and intelligent code modifications without context switching.