# MacMaint

AI-powered Mac maintenance and optimization CLI agent that keeps your Mac running smoothly.

## Features

- **Disk Space Management** - Automatically identifies and cleans caches, logs, and temporary files
- **Memory Optimization** - Monitors RAM usage and detects memory leaks
- **CPU Monitoring** - Tracks CPU-intensive processes and system load
- **AI-Powered Analysis** - Uses OpenAI GPT-4 to provide intelligent recommendations
- **Safety First** - Built-in safety checks and confirmation prompts for all destructive actions
- **Privacy Protected** - Anonymizes all data before sending to AI

## Installation

### Requirements

- macOS 11.0 or later
- Python 3.10+
- OpenAI API key (for AI analysis features)

### Quick Start

1. **Clone and install:**
   ```bash
   cd ~/projects
   git clone <repository-url> macmaint
   cd macmaint
   python3 -m venv venv
   source venv/bin/activate
   pip install -e .
   ```

2. **Initialize configuration:**
   ```bash
   macmaint init
   ```
   You'll be prompted for your OpenAI API key.

3. **Run your first scan:**
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
