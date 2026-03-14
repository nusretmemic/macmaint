# MacMaint Interactive Assistant - Quick Start Guide

## Overview

MacMaint now has a conversational AI assistant powered by GPT-4o. You can chat with it in natural language to scan, fix, and optimize your Mac.

## Getting Started

### 1. Start the Assistant

```bash
macmaint start
```

This launches an interactive session where you can chat with the AI.

### 2. Start a Fresh Conversation

```bash
macmaint start --new
```

This ignores previous conversations and starts fresh.

## What You Can Ask

### System Health Checks

```
"How is my Mac doing?"
"Check my system status"
"Is everything okay?"
```

**What it does:**
- Checks disk space, memory, and CPU
- Reports any critical issues
- Gives you a quick health summary

### Disk Space

```
"How much disk space do I have?"
"What's using my disk space?"
"Show me disk usage"
```

**What it does:**
- Shows free space
- Breaks down usage by category
- Suggests what can be cleaned

### System Scans

```
"Scan my Mac"
"Check for issues"
"Run a full scan"
```

**What it does:**
- Comprehensive system scan (~30 seconds)
- Checks disk, memory, CPU, startup items, caches
- Lists all issues found with severity levels

### Fixing Issues

```
"Fix the issues you found"
"Clean up my system"
"Help me free up space"
```

**What it does:**
- Reviews issues found in scan
- Asks which ones to fix (unless in trust mode)
- Executes fixes safely
- Reports what was done

### Maintenance Plans

```
"Create a maintenance schedule"
"What should I do regularly?"
"Give me a maintenance plan"
```

**What it does:**
- Creates personalized daily/weekly/monthly tasks
- Based on your usage patterns
- Helps you stay on top of maintenance

## Special Commands

### In-Session Commands

While chatting, you can use these special commands:

- **`help`** - Show available commands
- **`status`** - Show current session info
- **`history`** - Show conversation history
- **`clear`** - Clear screen
- **`exit`** - End session and exit

### Examples:

```
You: help
Assistant: [Shows help information]

You: status
Assistant: [Shows session details, trust mode, etc.]
```

## Trust Mode (Auto-Fix)

**Coming in a future update:** Trust mode lets the AI automatically fix safe issues without asking for permission each time.

For now, the AI will always ask before making changes.

## Conversation Features

### Multi-Turn Conversations

The AI remembers what you talked about:

```
You: Scan my Mac
AI: [Scans and finds issues]

You: Fix the cache issues
AI: [Fixes only cache-related issues]

You: What about the startup items?
AI: [Remembers and discusses startup items from scan]
```

### Session Persistence

Your conversations are saved between sessions:

```bash
# Day 1
macmaint start
You: Scan my Mac
AI: Found 3 issues...
You: exit

# Day 2
macmaint start
AI: Welcome back! Resuming your previous conversation...
You: Did we fix those issues?
AI: [Remembers the previous scan]
```

### Context-Aware Responses

The AI understands context:

```
You: My Mac is slow
AI: Let me check memory and CPU usage...

You: How is my Mac doing?
AI: [If scanned recently] Based on the scan from 2 minutes ago...
    [If not] Let me run a quick check...
```

## Example Conversations

### Example 1: Quick Health Check

```
You: How is my Mac doing?

AI: Let me run a quick health check...

    Your Mac is doing well overall! Here's the status:
    - Disk Space: 40 GB free (good)
    - Memory: 1.3 GB available (normal)
    - CPU: Low usage (no issues)
    
    No critical issues detected!
```

### Example 2: Disk Space Cleanup

```
You: I'm running out of disk space

AI: Let me analyze your disk usage...

    You have 15 GB free (72% used). Here's what's taking space:
    - Applications: 45 GB
    - Documents: 89 GB
    - Caches: 18 GB (can be cleaned!)
    
    I can free up about 15 GB by cleaning:
    - Browser caches (Chrome, Safari)
    - System caches
    - Old log files
    
    Would you like me to do that?

You: Yes, clean the caches

AI: Cleaning caches... [executes cleanup]
    
    Done! Freed up 14.2 GB:
    - Chrome caches: 6.8 GB
    - Safari caches: 3.1 GB
    - System caches: 4.3 GB
    
    You now have 29 GB free.
```

### Example 3: Performance Optimization

```
You: My Mac feels slow lately

AI: Let me check what might be causing that...

    I found a few things:
    - Memory is at 94% (high!)
    - 12 startup items (slowing boot time)
    - CPU is okay
    
    Top memory users:
    - Chrome: 3.2 GB
    - Slack: 1.8 GB
    - Docker: 2.1 GB
    
    I can help by:
    1. Optimizing memory (close unused apps)
    2. Reducing startup items
    3. Cleaning caches to free up swap space
    
    What would you like to tackle first?

You: Let's reduce the startup items

AI: [Shows startup items and helps disable unnecessary ones]
```

## Tips for Best Results

### Be Conversational

The AI understands natural language:
- ✅ "My disk is almost full, help!"
- ✅ "Check if everything's ok"
- ✅ "What's eating my memory?"

You don't need to use commands:
- ❌ `scan --quick`
- ✅ "Do a quick scan"

### Ask Follow-Up Questions

The AI remembers context:
```
You: Scan my Mac
AI: Found 5 issues...

You: Tell me more about the first one
You: Can you fix that?
You: What about the others?
```

### Be Specific When Needed

For complex requests:
- ✅ "Clean only browser caches"
- ✅ "Show me startup items but don't disable anything"
- ✅ "Scan but skip the network check"

### Let the AI Explain

Ask "why?" and "how?":
```
You: Why is this an issue?
You: What will fixing this do?
You: How does this work?
```

## Troubleshooting

### "No API key found"

```bash
# Set up your OpenAI API key
macmaint init

# Or manually:
echo "OPENAI_API_KEY=sk-..." >> ~/.macmaint/.env
```

### "Session interrupted"

Press Ctrl+C once to prompt exit, or twice to force quit.

### AI Not Responding

If the AI gets stuck:
1. Press Ctrl+C to cancel
2. Try rephrasing your question
3. Use `macmaint start --new` to start fresh

### Tools Failing

If tools report errors:
- Check permissions (System Settings > Privacy & Security)
- Run with verbose mode: `MACMAINT_DEBUG=true macmaint start`
- Some operations need admin privileges

## Privacy & Safety

### What Gets Sent to OpenAI

- Your messages to the AI
- **Anonymized** system metrics (no personal data)
- Tool execution results (anonymized)

### What Doesn't Get Sent

- Personal files or file contents
- Usernames, hostnames, paths
- API keys or credentials

### Safety Features

1. **Confirmation Required:** AI asks before making changes
2. **Dry Run Mode:** See what would change without doing it
3. **Undo Support:** Most operations can be undone
4. **Safe Defaults:** Conservative limits on deletions

## Advanced Usage

### Environment Variables

```bash
# Use a different OpenAI model
export MACMAINT_MODEL=gpt-4o

# Enable verbose debug output
export MACMAINT_DEBUG=true

# Custom API key (overrides .env)
export OPENAI_API_KEY=sk-...
```

### Configuration

Edit `~/.macmaint/config.yaml`:

```yaml
api:
  model: gpt-4o
  anonymize_data: true

safety:
  require_confirmation: true
  max_file_delete_count: 1000
```

## Getting Help

### In the Assistant

```
You: help
```

### Documentation

```bash
macmaint start --help
macmaint --help
```

### Feedback

Found a bug or have a suggestion?
- Report at: https://github.com/yourusername/macmaint/issues

## What's Next

**Coming Soon:**
- Trust mode (auto-fix safe issues)
- Sub-agents for complex workflows
- Trend analysis and predictions
- Scheduled maintenance
- Export reports

## Summary

MacMaint's interactive assistant makes Mac maintenance conversational and intelligent:

- 🗣️ **Natural Language:** Just talk to it
- 🧠 **Context-Aware:** Remembers your conversations
- 🔧 **Action-Oriented:** Fixes problems, not just describes them
- 🛡️ **Safe:** Asks before changing anything
- 📊 **Informative:** Explains what's happening and why

**Get started:** `macmaint start`

Enjoy your intelligent Mac maintenance assistant! 🚀
