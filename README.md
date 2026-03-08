# MacMaint

AI-powered Mac maintenance and optimization CLI agent that keeps your Mac running smoothly.

## Features

### Core Monitoring & Cleanup

- **Disk Space Management** - Automatically identifies and cleans caches, logs, and temporary files with detailed breakdown by category
- **Memory Optimization** - Monitors RAM usage, detects memory leaks, and categorizes processes by type
- **CPU Monitoring** - Tracks CPU-intensive processes and system load over time
- **Network Tracking** - Monitors bandwidth usage with anomaly detection
- **Battery Health** - Battery status and health monitoring (on laptops)
- **Startup Items** - Track launch agents and daemons

### AI-Powered Intelligence (Phase 2)

- **Conversational AI** - Ask questions about your Mac in natural language and get personalized answers
- **Issue Explanations** - Get detailed, context-aware explanations of system problems with actionable solutions
- **Proactive Insights** - AI predicts future issues and recommends optimal maintenance schedules
- **Smart Cleanup** - AI-powered risk assessment for safe file cleanup with personalized recommendations
- **Learning System** - Builds a profile of your usage patterns to provide increasingly relevant advice
- **Specialized AI Roles** - Choose from different AI personalities (General, Performance, Security, Storage, Maintenance, Troubleshooter)

### Safety & Privacy

- **Safety First** - Built-in safety checks and confirmation prompts for all destructive actions
- **Privacy Protected** - All data is anonymized before sending to AI
- **Smart Risk Assessment** - Cleanup recommendations with risk levels (SAFE, LOW_RISK, MEDIUM_RISK, HIGH_RISK, CRITICAL)
- **Local Profile Storage** - Your preferences and patterns are stored locally only

## Installation

### Requirements

- macOS 11.0 or later
- Python 3.10+
- OpenAI API key (for AI analysis features)

### Option 1: Install with Homebrew (Recommended)

```bash
brew tap nusretmemic/macmaint
brew install macmaint
```

Then initialize and run:
```bash
macmaint init
macmaint scan
```

### Option 2: Install with pipx

```bash
pip3 install pipx
pipx install git+https://github.com/nusretmemic/macmaint.git
```

### Option 3: Install from source

```bash
git clone https://github.com/nusretmemic/macmaint.git
cd macmaint
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### After Installation

1. **Initialize configuration:**
   ```bash
   macmaint init
   ```
   You'll be prompted for your OpenAI API key.

2. **Run your first scan:**
   ```bash
   macmaint scan
   ```

## Usage

### Commands

#### `macmaint init`
Initialize MacMaint with your OpenAI API key and create default configuration.

```bash
macmaint init
```

#### `macmaint scan`
Perform a full system scan and get AI-powered recommendations.

```bash
macmaint scan                    # Full scan with AI analysis
macmaint scan --no-ai            # Scan without AI (faster)
macmaint scan --verbose          # Show detailed metrics
```

#### `macmaint fix`
Interactively fix detected issues.

```bash
macmaint fix                     # Interactive mode with confirmations
macmaint fix --dry-run           # Simulate fixes without making changes
macmaint fix --yes               # Auto-confirm all actions (use with caution!)
```

#### `macmaint status`
Quick system health check.

```bash
macmaint status
```

#### `macmaint config`
View or modify configuration.

```bash
macmaint config                  # Show config file location
macmaint config ui.colors true   # Enable colors
```

#### `macmaint dashboard`
Show an interactive dashboard with system health overview and metrics visualization.

```bash
macmaint dashboard
```

#### `macmaint analyze-disk`
Detailed disk usage analysis with cache breakdown visualization.

```bash
macmaint analyze-disk             # Default tree view
macmaint analyze-disk --tree      # Tree view of cache breakdown
macmaint analyze-disk --table     # Table view of cache breakdown
```

#### `macmaint analyze-memory`
Detailed memory usage analysis with process categorization.

```bash
macmaint analyze-memory           # Basic memory breakdown
macmaint analyze-memory --processes  # Show processes by category
```

#### `macmaint trends`
View historical trends for system metrics with sparkline visualizations.

```bash
macmaint trends                   # Last 7 days
macmaint trends --days 30         # Last 30 days
```

### AI-Powered Commands (Phase 2)

MacMaint now includes intelligent AI features that learn from your behavior and provide personalized recommendations.

#### `macmaint ask`
Ask natural language questions about your Mac.

```bash
macmaint ask "Why is my Mac running slow?"
macmaint ask "How much space can I free up?"
macmaint ask "Which apps are using the most memory?"
```

The AI will analyze your current system state and provide helpful, personalized answers based on your usage patterns.

#### `macmaint explain`
Get a detailed explanation of a specific system issue.

```bash
macmaint explain                  # Shows list of current issues to select from
macmaint explain <issue-id>       # Explain specific issue by ID
```

The AI provides:
- Why the issue is occurring
- What the impact is on your system
- Step-by-step solutions
- Prevention tips for the future

#### `macmaint insights`
Get proactive insights and predictive recommendations.

```bash
macmaint insights
```

The AI analyzes your system patterns over time and provides:
- Predictions of future issues (e.g., "disk will be full in 14 days")
- Recommended maintenance schedule
- Optimization opportunities
- Trends in your system usage

### Example Workflow

```bash
# 1. Initial setup
macmaint init

# 2. Scan your system
macmaint scan

# Output:
# 🔴 CRITICAL (1 issue)
#   • Disk space critically low: 12.3 GB free (4.8%)
#     Recommendation: Clean caches and temporary files
#
# 🟡 WARNING (2 issues)
#   • High memory usage: Chrome (4.2 GB)
#   • Cache files consuming 8.4 GB
#
# Run 'macmaint fix' to address these issues

# 3. Fix issues interactively
macmaint fix

# Output:
# Issue 1/2: Cache files consuming 8.4 GB
# Found cache files that can be safely cleaned
# → Clean cache files (8.4 GB)
#   Impact: Free 8.4 GB
#   Proceed? [y/N]: y
# ✓ Cleaned 8.4 GB (1,247 files deleted)
```

### Example AI Workflow (Phase 2)

```bash
# 1. Ask a question about your Mac
macmaint ask "Why is my Mac running slow?"

# Output:
# ╭─ Answer ──────────────────────────────────────────╮
# │ Based on your current system state, your Mac is   │
# │ running slow due to:                              │
# │                                                   │
# │ 1. **High Memory Usage** (87% used)               │
# │    - Chrome is using 4.2 GB                       │
# │    - 15 background apps consuming 6.8 GB          │
# │                                                   │
# │ 2. **Disk Space Low** (12.3 GB free)              │
# │    - Browser caches: 3.2 GB                       │
# │    - System caches: 2.1 GB                        │
# │                                                   │
# │ **Recommendations:**                              │
# │ - Close unused Chrome tabs or restart Chrome      │
# │ - Run `macmaint fix` to clean caches              │
# │ - Consider upgrading storage if this happens oft  │
# ╰───────────────────────────────────────────────────╯

# 2. Get detailed explanation of a specific issue
macmaint explain

# Output: (shows list of issues to select from)
# Available Issues:
#   1. 🔴 High memory usage: Chrome (4.2 GB)
#   2. 🟡 Cache files consuming 8.4 GB
# Select issue number [1]: 1

# ╭─ High memory usage: Chrome (4.2 GB) ─────────────╮
# │ ## What's Happening                               │
# │ Chrome is consuming 4.2 GB of RAM...              │
# │                                                   │
# │ ## Why It Matters                                 │
# │ High memory usage can slow down your entire...    │
# │                                                   │
# │ ## How to Fix                                     │
# │ 1. Close unnecessary tabs...                      │
# │ 2. Disable unused extensions...                   │
# ╰───────────────────────────────────────────────────╯

# 3. Get proactive insights
macmaint insights

# Output:
# ╭─ AI Insights & Recommendations ───────────────────╮
# │ ## Predictions                                    │
# │ - **Disk Full Warning:** At current usage rate,   │
# │   your disk will be full in ~14 days              │
# │                                                   │
# │ ## Maintenance Schedule                           │
# │ Based on your patterns, I recommend:              │
# │ - Weekly cache cleanup (you typically clean       │
# │   every 12 days)                                  │
# │ - Monthly memory optimization                     │
# │                                                   │
# │ ## Optimization Opportunities                     │
# │ - You frequently ignore "large downloads" issues  │
# │   Consider moving old downloads to external drive │
# ╰───────────────────────────────────────────────────╯
```

## User Profile & Learning

MacMaint builds a profile of your usage patterns to provide increasingly personalized recommendations. The profile is stored locally in `~/.macmaint/profile.json` and includes:

- **Preferences**: Risk tolerance, preferred AI role, notification level
- **Usage Patterns**: Most common issues, cleanup frequency, fix history
- **Learning Data**: Which issues you tend to fix vs. ignore, recurring problems

### Profile Customization

The AI automatically learns from your actions, but you can also customize preferences:

```yaml
# In ~/.macmaint/profile.json (automatically created)
{
  "preferences": {
    "risk_tolerance": "conservative",        # conservative, moderate, aggressive
    "preferred_ai_role": "general",          # general, performance, security, storage, maintenance, troubleshooter
    "auto_fix_safe_issues": false,
    "show_technical_details": false,
    "notification_level": "important"        # all, important, critical
  }
}
```

### AI Roles

MacMaint offers different AI personalities to match your needs:

- **General**: Balanced advice for everyday Mac users (default)
- **Performance**: Focused on speed and optimization
- **Security**: Privacy and security-focused recommendations
- **Storage**: Disk space management specialist
- **Maintenance**: Preventive care and system health
- **Troubleshooter**: Problem-solving and issue resolution

## Configuration

MacMaint stores its configuration in `~/.macmaint/config.yaml`.

### Key Settings

```yaml
# API Configuration
api:
  provider: openai
  model: gpt-4-turbo
  anonymize_data: true

# Module Settings
modules:
  disk:
    enabled: true
    cache_age_days: 30
    large_file_threshold_mb: 500
    exclude_paths:
      - ~/Documents
      - ~/Desktop
      - ~/Pictures

  memory:
    enabled: true
    alert_threshold_percent: 85

  cpu:
    enabled: true
    alert_threshold_percent: 80
    sample_duration_seconds: 5

# Safety Settings
safety:
  require_confirmation: true
  max_file_delete_count: 1000
  max_space_to_free_gb: 50
```

## Safety Features

MacMaint is designed with safety as a top priority:

- **Protected Paths** - Never touches system directories or user documents without explicit confirmation
- **Confirmation Prompts** - All destructive actions require user approval
- **Dry Run Mode** - Test fixes without making any changes
- **Data Anonymization** - Removes sensitive information before sending to AI
- **File Count Limits** - Prevents accidentally deleting large numbers of files
- **Space Limits** - Caps the amount of space that can be freed in one operation

### Protected Paths (Never Modified)

- `/System/`
- `/Library/Apple/`
- `/bin/`, `/sbin/`, `/usr/bin/`, `/usr/sbin/`
- `/private/var/db/`

### Sensitive Paths (Require Confirmation)

- `~/Documents/`
- `~/Desktop/`
- `~/Pictures/`
- `~/Music/`
- `~/Movies/`
- `~/Downloads/`

## How It Works

1. **Scanning** - MacMaint collects metrics from disk, memory, and CPU modules
2. **Analysis** - Metrics are analyzed locally to detect common issues
3. **AI Enhancement** - Anonymized data is sent to OpenAI for intelligent recommendations
4. **Interactive Fixing** - User reviews and approves fixes interactively
5. **Execution** - Approved fixes are executed with full safety checks

## Privacy

MacMaint takes privacy seriously:

- **Local Analysis** - Most analysis happens on your Mac
- **Anonymization** - All usernames, paths, UUIDs, and serial numbers are anonymized before sending to OpenAI
- **No Tracking** - MacMaint doesn't collect or send any telemetry
- **Open Source** - All code is available for review

### What Gets Anonymized

- Usernames → `<USER>`
- File paths → `/Users/<USER>/...`
- UUIDs → `<UUID>`
- MAC addresses → `<MAC>`
- IP addresses → `<IP>`
- Serial numbers → `<SERIAL>`

### What Gets Sent to OpenAI

- Disk space metrics (total, used, free percentages)
- Memory usage metrics
- CPU usage metrics
- File types and sizes (not names or paths)
- Process names (not arguments or user data)

## Troubleshooting

### "No API key found"

Run `macmaint init` to set up your OpenAI API key, or set the `OPENAI_API_KEY` environment variable.

### "Permission denied" errors

Some system operations require elevated permissions. MacMaint will skip files it can't access.

### Slow scans

The CPU module samples for 5 seconds by default. You can reduce this in the config:
```yaml
modules:
  cpu:
    sample_duration_seconds: 2
```

### AI analysis fails

If AI analysis fails, MacMaint will continue with local analysis only. Check your API key and internet connection.

## Development

### Running Tests

```bash
pytest tests/
```

### Project Structure

```
macmaint/
├── src/macmaint/
│   ├── cli.py              # CLI interface
│   ├── config.py           # Configuration management
│   ├── modules/            # Monitoring modules
│   │   ├── disk.py
│   │   ├── memory.py
│   │   └── cpu.py
│   ├── ai/                 # AI integration
│   │   ├── client.py
│   │   ├── prompts.py
│   │   └── anonymizer.py
│   ├── core/               # Core logic
│   │   ├── scanner.py
│   │   └── fixer.py
│   └── utils/              # Utilities
│       ├── formatters.py
│       ├── safety.py
│       └── system.py
└── tests/                  # Test suite
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details.

## Disclaimer

MacMaint is provided as-is. While we've implemented extensive safety checks, always review what the tool plans to do before confirming any actions. Back up important data regularly.

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

---

**Made with care for Mac users who want their systems to run smoothly** 🚀
