# Release Notes - v0.3.0

## Phase 2: AI-Powered Intelligence & Personalization

This major update transforms MacMaint from a monitoring tool into an intelligent assistant that learns from your behavior and provides personalized recommendations.

### 🎯 New Features

#### AI Conversational Commands

**`macmaint ask`** - Ask natural language questions about your Mac
- Get personalized answers based on your current system state
- Context-aware responses that consider your usage patterns
- Example: `macmaint ask "Why is my Mac running slow?"`

**`macmaint explain`** - Get detailed explanations of system issues
- Deep dive into specific problems with actionable solutions
- Interactive issue selection from current scan results
- Includes prevention tips and recovery options
- Example: `macmaint explain` (shows list) or `macmaint explain <issue-id>`

**`macmaint insights`** - Proactive insights and predictive analysis
- AI predicts future issues based on historical trends
- Recommended maintenance schedules tailored to your usage
- Optimization opportunities based on your patterns
- Example: `macmaint insights`

#### User Profile & Learning System

**Automatic Learning**
- Tracks which issues you fix vs. ignore
- Learns your cleanup preferences and frequency
- Identifies recurring problems
- Builds personalized recommendations over time
- Profile stored locally at `~/.macmaint/profile.json`

**Preference Customization**
- Risk tolerance levels: conservative, moderate, aggressive
- AI role selection: general, performance, security, storage, maintenance, troubleshooter
- Technical detail preferences
- Notification levels
- Auto-fix safe issues option

**Ignored Issues**
- Issues you skip are automatically tracked
- Frequently ignored issue types won't bother you again
- Can manually manage ignored issues in profile

#### Specialized AI Roles

Choose the AI personality that matches your needs:
- **General**: Balanced advice for everyday users (default)
- **Performance**: Speed and optimization focused
- **Security**: Privacy and security recommendations
- **Storage**: Disk space management specialist
- **Maintenance**: Preventive care and system health
- **Troubleshooter**: Problem-solving expert

#### Smart Cleanup Analyzer

**AI-Powered Risk Assessment**
- Analyzes files before cleanup with risk levels:
  - SAFE: Can delete without any impact
  - LOW_RISK: Minimal risk, easily recoverable
  - MEDIUM_RISK: Some risk, may require re-download
  - HIGH_RISK: Significant risk, could cause data loss
  - CRITICAL: Do not delete without explicit confirmation
- Personalized recommendations based on your risk tolerance
- Context-aware cleanup suggestions

**File Categorization**
- Browser caches (with re-login warnings)
- System caches
- Application caches
- Log files
- Downloads
- Each category has appropriate risk assessment

### 🔧 Improvements

**Enhanced Scanner**
- Integrates user profile for personalized analysis
- Filters out issues you've chosen to ignore
- Uses your preferred AI role for analysis
- Tracks scan frequency automatically

**Enhanced Fixer**
- Tracks all fix actions to user profile
- Records skipped issues as "ignored"
- Learns from your fix patterns
- Better issue categorization

**Historical Data Integration**
- Insights command uses up to 30 days of historical data
- Trend-based predictions
- Pattern recognition for recurring issues

### 📊 Profile Statistics

MacMaint now tracks:
- Total scans performed
- Total fixes applied
- Most common issues in your system
- Frequently ignored issue types
- Cleanup frequency (days between cleanups)
- Recurring issue counts
- Fix success history

### 🎨 User Experience

**Personalized Recommendations**
- AI responses adapt to your technical level
- Suggestions based on your fix history
- Warnings for issues you typically ignore
- Language style matches your preferences

**Better Context Awareness**
- AI considers your system's historical trends
- Recommendations factor in your usage patterns
- Issue explanations tailored to your knowledge level

### 🔒 Privacy & Safety

**Local Storage**
- All profile data stored locally in `~/.macmaint/`
- No user data sent to external servers (except anonymized metrics to AI)
- Profile is under your control

**Conservative Defaults**
- Risk tolerance defaults to "conservative"
- AI role defaults to "general" (balanced)
- Auto-fix disabled by default
- Confirmation prompts remain enabled

### 📝 Technical Details

**New Files**
- `src/macmaint/utils/profile.py` - User profile system with ProfileManager
- `src/macmaint/ai/cleanup.py` - Smart cleanup analyzer with risk assessment
- Enhanced `src/macmaint/ai/prompts.py` - 6 specialized AI roles with role-specific prompts
- Enhanced `src/macmaint/ai/client.py` - 4 new AI methods (ask, explain, cleanup, insights)

**Updated Files**
- `src/macmaint/cli.py` - Added 3 new commands (ask, explain, insights)
- `src/macmaint/core/scanner.py` - Integrated profile for personalized analysis
- `src/macmaint/core/fixer.py` - Added profile tracking for user actions

**Dependencies**
- No new dependencies required
- Uses existing OpenAI API integration
- Python 3.10+ required (unchanged)

### 🐛 Bug Fixes

- None (this is a feature release)

### 📚 Documentation

- Updated README with Phase 2 features
- Added AI command examples
- Documented user profile system
- Added AI role descriptions
- Included example workflows for new commands

### 🚀 Migration from v0.2.0

**Automatic**
- Profile will be created automatically on first scan with v0.3.0
- All existing functionality remains unchanged
- New commands are additive, not breaking

**No Action Required**
- Existing scans, configs, and history remain compatible
- API key and configuration carry over
- No data migration needed

### 📈 What's Next

**Future Phases:**
- Phase 3: Advanced automation and scheduling
- Phase 4: Cross-system analytics and recommendations
- Phase 5: Integration with macOS system services

---

## Upgrade Instructions

### Via Homebrew
```bash
brew update
brew upgrade macmaint
```

### Via pip/pipx
```bash
pipx upgrade macmaint
# or
pip install --upgrade macmaint
```

### From Source
```bash
cd macmaint
git pull origin main
pip install -e .
```

---

## Compatibility

- macOS 11.0+ (unchanged)
- Python 3.10+ (unchanged)
- OpenAI API key required for AI features (unchanged)

---

## Credits

Built with love for the Mac community. Special thanks to all beta testers and contributors.

**Note**: This is a free and open-source project. If you find it useful, please star the repo and share with others!
