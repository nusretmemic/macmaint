# MacMaint v0.5.0

AI-powered macOS maintenance CLI agent — have a conversation with your Mac.

```
 ███╗   ███╗ █████╗  ██████╗███╗   ███╗ █████╗ ██╗███╗   ██╗████████╗
 ████╗ ████║██╔══██╗██╔════╝████╗ ████║██╔══██╗██║████╗  ██║╚══██╔══╝
 ██╔████╔██║███████║██║     ██╔████╔██║███████║██║██╔██╗ ██║   ██║
 ██║╚██╔╝██║██╔══██║██║     ██║╚██╔╝██║██╔══██║██║██║╚██╗██║   ██║
 ██║ ╚═╝ ██║██║  ██║╚██████╗██║ ╚═╝ ██║██║  ██║██║██║ ╚████║   ██║
 ╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝
```

---

## What is MacMaint?

MacMaint is a conversational AI agent for macOS system maintenance. Instead of running one-off commands and reading tables of numbers, you open a REPL and **talk to your Mac**. The orchestrator (GPT-4o) coordinates three specialised sub-agents — ScanAgent, FixAgent, and AnalysisAgent — and surfaces actionable, context-aware answers.

```
$ macmaint chat

  MacMaint v0.5.0  —  type 'help' or just ask a question

  you > Why is my Mac slow today?

  ⠸ Scanning system...  (1.2s)
  ⠸ Analysing patterns...  (0.8s)

 ╭─ MacMaint ──────────────────────────────────────────────────────────╮
 │                                                                     │
 │  Three things are contributing right now:                           │
 │                                                                     │
 │  1. Memory pressure is high (87 %). Chrome has 14 renderer          │
 │     processes open consuming 4.8 GB combined.                       │
 │                                                                     │
 │  2. Disk is 94 % full (only 15 GB free). macOS needs ~10 % free     │
 │     for virtual memory swap — you're cutting it close.              │
 │                                                                     │
 │  3. Compile jobs from Xcode are pinning two CPU cores               │
 │     (combined 180 % usage for the last 5 minutes).                  │
 │                                                                     │
 │  Quick wins: run `macmaint fix` to reclaim ~8 GB of caches,         │
 │  or tell me "clean caches" and I'll walk you through it.            │
 │                                                                     │
 ╰─────────────────────────────────────────────────────────────────────╯

  you > clean caches

  ⠸ Identifying safe targets...  (0.6s)

 ╭─ Proposed actions ──────────────────────────────────────────────────╮
 │  • Browser caches     3.2 GB   SAFE                                 │
 │  • System log files   1.1 GB   SAFE                                 │
 │  • Xcode DerivedData  4.0 GB   LOW_RISK                             │
 │  Total recoverable:   8.3 GB                                        │
 ╰─────────────────────────────────────────────────────────────────────╯

  Proceed with all three? [Y/n]:
```

---

## Installation

### Option 1 — Homebrew (recommended)

```bash
brew tap nusretmemic/macmaint
brew install macmaint
macmaint init          # enter your OpenAI API key once
macmaint chat          # start the REPL
```

### Option 2 — pipx

```bash
pipx install git+https://github.com/nusretmemic/macmaint.git
macmaint init
macmaint chat
```

### Option 3 — from source

```bash
git clone https://github.com/nusretmemic/macmaint.git
cd macmaint
python3 -m venv venv && source venv/bin/activate
pip install -e .
macmaint init
macmaint chat
```

### Requirements

- macOS 11.0 (Big Sur) or later
- Python 3.10+
- OpenAI API key

---

## Setup

```bash
macmaint init
```

This creates `~/.macmaint/` with:

```
~/.macmaint/
├── .env            # OPENAI_API_KEY stored here
├── config.yaml     # tunable settings
├── profile.json    # your usage profile (local only)
├── history/        # metric snapshots for trend analysis
└── conversations/  # session transcripts
```

---

## Commands

| Command | What it does |
|---------|-------------|
| `macmaint init` | First-time setup — API key, config, directories |
| `macmaint chat` | Open the conversational AI REPL (main interface) |
| `macmaint scan` | One-shot system scan + AI recommendations |
| `macmaint fix` | Interactive issue fixer |
| `macmaint status` | Quick health snapshot |
| `macmaint dashboard` | Live Rich dashboard with sparklines |
| `macmaint analyze-disk` | Detailed disk breakdown (tree or table) |
| `macmaint analyze-memory` | Memory breakdown + process categories |
| `macmaint trends [--days N]` | Historical metric trends |
| `macmaint ask "..."` | Single-shot question (no REPL) |
| `macmaint explain [issue-id]` | Deep-dive explanation of a specific issue |
| `macmaint insights` | Predictive recommendations |
| `macmaint config [key value]` | View or set config values |

### Trust mode

Pass `--yes` to `fix` to auto-confirm all **SAFE** actions without prompts:

```bash
macmaint fix --yes
```

Pass `--dry-run` to simulate without touching anything:

```bash
macmaint fix --dry-run
```

---

## Architecture

```
macmaint chat
      │
      ▼
  Orchestrator  (GPT-4o)
  ┌─────────────────────────────────────────────┐
  │  • Interprets user intent                   │
  │  • Routes to sub-agents                     │
  │  • Merges results into a coherent response  │
  └───────┬─────────────┬─────────────┬─────────┘
          │             │             │
          ▼             ▼             ▼
     ScanAgent     FixAgent    AnalysisAgent
    (GPT-4o-mini) (GPT-4o-mini) (GPT-4o-mini)
          │             │             │
          ▼             ▼             ▼
     disk / mem    safety +      trends +
     cpu / net     fixer.py      profile.json
     battery /     execution     history/
     startup
```

All three sub-agents call into the same `ToolExecutor` layer, which reads live system metrics from the monitoring modules and enforces safety rules before any write operation.

---

## Privacy

| Data | Where it goes |
|------|--------------|
| Disk/memory/CPU percentages | OpenAI (anonymised) |
| File types and sizes | OpenAI (no names or paths) |
| Process names | OpenAI (no arguments) |
| Usernames, file paths, UUIDs, MACs, IPs, serial numbers | **Stripped before leaving your Mac** |
| Your profile and history | **Local only — never sent** |

Anonymisation substitutions:

```
/Users/alice/Documents  →  /Users/<USER>/Documents
550e8400-...            →  <UUID>
192.168.1.1             →  <IP>
C8:89:F3:...            →  <MAC>
```

---

## Configuration

`~/.macmaint/config.yaml` — key settings:

```yaml
api:
  provider: openai
  model: gpt-4o
  anonymize_data: true

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

safety:
  require_confirmation: true
  max_file_delete_count: 1000
  max_space_to_free_gb: 50
```

### Profile preferences (`~/.macmaint/profile.json`)

```json
{
  "preferences": {
    "risk_tolerance": "conservative",
    "preferred_ai_role": "general",
    "auto_fix_safe_issues": false,
    "show_technical_details": false,
    "notification_level": "important"
  }
}
```

`preferred_ai_role` options: `general`, `performance`, `security`, `storage`, `maintenance`, `troubleshooter`

---

## Safety

Protected paths — never modified without explicit override:

- `/System/`, `/Library/Apple/`
- `/bin/`, `/sbin/`, `/usr/bin/`, `/usr/sbin/`
- `/private/var/db/`

Sensitive paths — always require confirmation:

- `~/Documents/`, `~/Desktop/`, `~/Pictures/`
- `~/Music/`, `~/Movies/`, `~/Downloads/`

Risk levels used throughout: `SAFE`, `LOW_RISK`, `MEDIUM_RISK`, `HIGH_RISK`, `CRITICAL`

---

## Development

```bash
git clone https://github.com/nusretmemic/macmaint.git
cd macmaint
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v          # 67 tests
```

### Project layout

```
macmaint/
├── src/macmaint/
│   ├── cli.py                    # Click entry points
│   ├── config.py                 # Config + .env loading
│   ├── assistant/
│   │   ├── orchestrator.py       # GPT-4o orchestrator
│   │   ├── agents.py             # ScanAgent / FixAgent / AnalysisAgent
│   │   ├── tools.py              # ToolExecutor — bridges agents → modules
│   │   ├── prompts.py            # System prompts
│   │   ├── repl.py               # Rich REPL (live spinners, colour panels)
│   │   └── session.py            # Session management + history
│   ├── core/
│   │   ├── scanner.py
│   │   └── fixer.py
│   ├── modules/                  # disk / memory / cpu / network / battery / startup
│   └── utils/
│       ├── formatters.py
│       ├── history.py
│       ├── profile.py
│       └── safety.py
└── tests/
    ├── conftest.py
    ├── test_session.py           # 18 tests
    ├── test_tools.py             # 21 tests
    ├── test_agents.py            # 16 tests
    └── test_integration.py       # 12 tests
```

---

## Changelog

### v0.5.0 (2026-03-14)
- Full CLI UI overhaul: Rich `Live` animated spinners, ASCII wordmark banner, colour-coded response panels, per-tool elapsed-time counters
- Fix: `ToolExecutor` was reading wrong Pydantic field names (`usage_percent`, `breakdown`) — all metrics silently reported 0. Corrected to `percent_used`, `cpu_percent`, `cache_breakdown`
- Fix: session IDs used second-precision timestamps; concurrent sessions collided. Added microsecond suffix (`%f`) to strftime format
- 67-test suite covering session management, tool execution, agent behaviour, and end-to-end integration

### v0.4.0
- Multi-agent architecture: Orchestrator + ScanAgent + FixAgent + AnalysisAgent
- Conversational REPL (`macmaint chat`)
- Session persistence and conversation history

### v0.3.0
- Proactive insights and trend prediction
- User profile learning system
- AI roles (general, performance, security, storage, maintenance, troubleshooter)

### v0.2.0
- `macmaint ask` and `macmaint explain` commands
- Data anonymisation layer
- OpenAI integration with retry/fallback

### v0.1.0
- Core monitoring modules: disk, memory, CPU, network, battery, startup
- `macmaint scan`, `macmaint fix`, `macmaint status`
- Safety system with protected/sensitive path lists

---

## License

MIT — see `LICENSE` for details.

## Contributing

Issues and PRs are welcome at https://github.com/nusretmemic/macmaint

## Disclaimer

MacMaint is provided as-is. Always review proposed actions before confirming. Back up important data regularly.
