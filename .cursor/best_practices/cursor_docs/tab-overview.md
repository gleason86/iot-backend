# Tab System - Complete Reference

## Overview

Tab is Cursor's specialized AI model for intelligent autocompletion and code assistance. Unlike traditional autocomplete, Tab learns from your coding patterns and provides context-aware, multi-line suggestions that improve over time.

**URL**: https://cursor.com/docs/tab/overview
**Section**: Core

## Key Features

### Intelligent Suggestions
- **Context-aware completions** based on recent edits, linter errors, and accepted changes
- **Multi-line modifications** that span multiple lines of code
- **Import statement addition** when missing dependencies are detected
- **Cross-file coordination** for related code changes

### Acceptance Controls
- **Accept**: `Tab` key to accept full suggestion
- **Reject**: `Esc` key to dismiss suggestion
- **Partial Accept**: `Ctrl+Arrow Right` (word-by-word acceptance)
- **Continue Typing**: Keep typing to refine suggestions

## Core Functionality

### 1. Basic Suggestions
**How it works:**
- Displays as semi-opaque "ghost text" when adding new code
- Shows as diff popup when modifying existing code
- Learns from your acceptance/rejection patterns

**Visual Indicators:**
- Ghost text for insertions
- Diff preview for modifications
- Portal windows for cross-file suggestions

### 2. Jump in File
**Predictive Navigation:**
- Anticipates next editing location within current file
- Suggests logical next steps after accepting an edit
- Press `Tab` again after accepting to jump to predicted location

**Use Cases:**
- Method chaining completion
- Property access sequences
- Error handling additions
- Test case expansions

### 3. Jump Across Files
**Cross-File Intelligence:**
- Predicts context-aware edits in related files
- Shows portal window at bottom when cross-file jump suggested
- Maintains workflow continuity across file boundaries

**Benefits:**
- Seamless refactoring across modules
- API contract updates (interface + implementation)
- Test file synchronization
- Configuration consistency

### 4. Auto-Import
**Automatic Dependency Management:**
- Detects missing imports in TypeScript and Python
- Suggests appropriate import statements
- Adds imports without disrupting coding flow

**Supported Languages:**
- **TypeScript**: Full import statement generation
- **Python (beta)**: Module and function imports

**Troubleshooting:**
- Ensure correct language server/extensions are installed
- Test with `Ctrl+.` to verify Quick Fix suggestions appear
- Check project configuration for proper module resolution

### 5. Tab in Peek
**Definition View Integration:**
- Works in "Go to Definition" and "Go to Type Definition" peek views
- Enables function signature modifications
- Supports call site updates during refactoring

**Vim Integration:**
- Use `gd` to jump to definitions
- Modify signatures and resolve references in one workflow

### 6. Partial Accepts
**Granular Control:**
- Accept suggestions word-by-word with `Ctrl+Arrow Right`
- Customizable via `editor.action.inlineSuggest.acceptNextWord` keybinding
- Enable in: `Cursor Settings → Tab → Partial Accepts`

## Configuration Settings

| Setting | Description |
|---------|-------------|
| **Cursor Tab** | Context-aware, multi-line suggestions around cursor based on recent edits |
| **Partial Accepts** | Accept next word of suggestion via `Ctrl+Arrow Right` |
| **Suggestions While Commenting** | Enable Tab inside comment blocks |
| **Whitespace-Only Suggestions** | Allow edits affecting only formatting |
| **Imports** | Enable auto-import for TypeScript |
| **Auto Import for Python (beta)** | Enable auto-import for Python projects |

## Toggling Controls

**Status Bar Options (bottom-right):**
- **Snooze**: Temporarily disable Tab for chosen duration
- **Disable globally**: Disable Tab for all files
- **Disable for extensions**: Disable Tab for specific file extensions (e.g., markdown, JSON)

## FAQ

### Tab gets in the way when writing comments, what can I do?
- Use **"Disable for extensions"** to exclude comment-heavy file types
- Toggle **"Suggestions While Commenting"** setting off
- Use **Snooze** feature for focused comment-writing sessions

### Can I change the keyboard shortcut for Tab suggestions?
- Default: `Tab` to accept, `Esc` to reject
- Partial accepts: `Ctrl+Arrow Right` (configurable)
- Custom keybindings available in Cursor Settings

### How does Tab generate suggestions?
- **Learns from patterns**: Recent edits, accepted/rejected suggestions, coding style
- **Context awareness**: Current file, cursor position, surrounding code
- **Multi-signal input**: Linter errors, recent changes, project structure
- **Iterative improvement**: Gets better as you use it and provide feedback

## Advanced Usage Patterns

### Refactoring Workflows
1. Start with high-level change description
2. Accept Tab suggestions for initial implementation
3. Use cross-file jumps to update related code
4. Leverage auto-import for new dependencies

### API Development
1. Define interface/function signature
2. Tab suggests implementation structure
3. Jump to test files for corresponding updates
4. Auto-import handles dependency management

### Debugging Sessions
1. Tab suggests error handling patterns
2. Jump to logging locations
3. Update error messages across files
4. Maintain consistency in error responses

## Performance Considerations

### Learning Curve
- **Initial suggestions** may be basic but improve rapidly
- **Pattern recognition** gets better with consistent usage
- **Context understanding** deepens with project familiarity

### Resource Usage
- **Local processing** with minimal latency impact
- **Incremental learning** without full model retraining
- **Selective application** via toggling controls

## Integration Points

### With Other Cursor Features
- **Agent**: Tab suggestions can be applied before agent execution
- **Rules**: Custom rules can enhance Tab suggestions
- **Context**: Indexing improves cross-file suggestions
- **Bugbot**: Error detection influences Tab suggestions

### IDE Compatibility
- **Native integration** with Cursor's editing experience
- **Vim mode support** with `gd` navigation
- **Peek view integration** for definition modifications
- **Multi-cursor support** for bulk edits

## Best Practices

### Training Tab Effectively
1. **Consistent acceptance patterns** - Accept good suggestions, reject poor ones
2. **Regular usage** - The more you use Tab, the better it becomes
3. **Clear intent signals** - Your accept/reject decisions teach the model

### Workflow Optimization
1. **Combine with agents** - Use Tab for quick edits, agents for complex tasks
2. **Leverage jumps** - Let Tab guide your navigation between related code
3. **Trust the process** - Tab gets better as it learns your patterns

### When to Disable
1. **Comment writing** - Use extension-specific disabling
2. **Creative writing** - Disable for prose or documentation
3. **Highly structured code** - When following strict templates

## Troubleshooting

### Common Issues
- **Suggestions not appearing**: Check if Tab is enabled in status bar
- **Poor suggestions**: May need more training data from your codebase
- **Import issues**: Verify language server configuration
- **Performance lag**: Consider disabling for large files or specific extensions

### Recovery Steps
1. **Restart Tab learning**: Clear recent context by restarting Cursor
2. **Reset settings**: Re-enable core Tab functionality
3. **Check extensions**: Ensure compatible language servers are installed
4. **Update Cursor**: Ensure you're on latest version for best performance

## Future Developments

Tab continues to evolve with:
- **Enhanced multi-file understanding**
- **Better language support expansion**
- **Improved learning algorithms**
- **Deeper IDE integration**

This system represents Cursor's commitment to fluid, intelligent coding assistance that adapts to individual developer workflows and preferences.