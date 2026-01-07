# Ledger Audit Guide

## Overview

The ledger audit system detects gaps between filesystem reality and ledger documentation. This guide explains how to interpret audit output and take action.

## Running Audits

### Manual Audit
```bash
./scripts/ledger-audit.sh
```

### AI Workbench Sync (last 7 days)
```bash
./scripts/sync-ai-workbench.sh
```

### Automated Weekly Audit
```bash
# Install launchd job (macOS)
# See "Scheduling" section below
```

## Understanding Output

### Section 1: Repos Not in repos.yaml

**What it detects:** Directories in `~/Desktop/projects/` not documented in `ledger/projects/repos.yaml`

**Example:**
```
1. Repos in ~/Desktop/projects/ not in repos.yaml:
  ❌ kyleos (exists but not in ledger)
```

**Action:** Add to `repos.yaml`:
```yaml
- name: "KyleOS"
  repo_path: "/Users/kylejensen/Desktop/projects/kyleos"
  status: ACTIVE
  note: "Description here"
```

### Section 2: AI Workbench Projects Not in Ledger

**What it detects:** Projects in `~/Documents/ai-workbench/ai-scrapbook/` not in ledger

**Example:**
```
2. ai-workbench projects not in ledger:
  ❌ business-ideas (ai-workbench but not in ledger)
```

**Action:**
- If it's a repo → add to `repos.yaml`
- If it's a business idea → add to `ideas.yaml`
- If it's notes/archive → skip (documentation not required)

### Section 3: Status Consistency Checks

**What it detects:** Conflicts between `repos.yaml` and `business_models.yaml`

**Example:**
```
3. Status consistency checks:
  ⚠️  Accounting OS: business_models.yaml says 'design' but repos.yaml says 'SHELVED'
```

**Action:** Align statuses:
- If actively working → both should show ACTIVE/design
- If paused → both should show PAUSED/paused
- If abandoned → both should show SHELVED/abandoned

### Section 4: Stale Priorities

**What it detects:** Ideas marked priority_rank: 1 but no action >30 days

**Example:**
```
4. Stale priorities (>30 days, 0 conversations):
  ❌ CMMC Compliance (priority #1, captured 198 days ago, 0 customer conversations)
```

**Action:**
- Take action: Schedule customer interviews, do market research
- Deprioritize: Remove `priority_rank` or change to lower number
- Archive: Move to status: shelved if no longer relevant

### Section 5: Complete Projects With 0 Sales

**What it detects:** Projects marked ARCHIVED/COMPLETE without sales validation

**Example:**
```
5. Complete projects with 0 sales attempts:
  ⚠️  OSHA 300 Compliance Automation (ARCHIVED/COMPLETE, no sales validation)
```

**Action:**
- Attempt to monetize: Create landing page, reach out to potential customers
- Document non-commercial: Add note explaining why not for sale
- Accept sunk cost: Add lesson_learned to project entry

## Pre-Commit Hook

The pre-commit hook runs automatically on `git commit` when ledger files change.

**What it validates:**
- repos.yaml ↔ business_models.yaml consistency
- business_models.yaml mentions → repos.yaml existence
- ideas.yaml priority_rank → next_step presence

**Example warning:**
```
⚠️  Warning: repos.yaml shows ACTIVE but business_models.yaml shows paused
Consider updating both files for consistency
```

**Action:**
- Fix inconsistencies before committing
- Or commit with warning if intentional temporary state

## Scheduling Automated Audits

### macOS (launchd)

Create `~/Library/LaunchAgents/com.operator.ledger-audit.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.operator.ledger-audit</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/kylejensen/Desktop/operator/scripts/ledger-audit.sh</string>
    </array>
    <key>StandardOutPath</key>
    <string>/Users/kylejensen/Desktop/operator/ledger/logs/audit-latest.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/kylejensen/Desktop/operator/ledger/logs/audit-latest.log</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</dict>
</plist>
```

Load the job:
```bash
launchctl load ~/Library/LaunchAgents/com.operator.ledger-audit.plist
```

Verify:
```bash
launchctl list | grep ledger-audit
```

### Linux/Cron

Add to crontab:
```bash
crontab -e

# Add line:
0 9 * * 0 /Users/kylejensen/Desktop/operator/scripts/ledger-audit.sh >> /Users/kylejensen/Desktop/operator/ledger/logs/audit-$(date +\%Y-\%m-\%d).log 2>&1
```

## Gap Closure Workflow

1. **Run audit:** `./scripts/ledger-audit.sh`
2. **Review gaps:** Read output sections 1-5
3. **Prioritize:** Which gaps matter most?
4. **Take action:**
   - Add to repos.yaml (repos in ~/Desktop/projects/)
   - Add to ideas.yaml (business ideas)
   - Update status consistency
   - Act on stale priorities or deprioritize
   - Monetize complete projects or document why not
5. **Re-run audit:** Verify gaps closed

## Integration with Issue-Driven Development

Gaps detected by audit can become issues:

**Example:** If audit finds kyleos repo not in ledger:

Create issue:
```markdown
feat: Add kyleos to repos.yaml

**Files:** `./ledger/projects/repos.yaml`
**Estimate:** 15min

## Problem
kyleos exists in ~/Desktop/projects/ but not documented in ledger

## Implementation
Add entry to repos.yaml:
- name: "KyleOS"
  repo_path: "/Users/kylejensen/Desktop/projects/kyleos"
  status: [determine status]

## Verification
./scripts/ledger-audit.sh
# Should not show kyleos gap

## Done When
- [ ] kyleos entry added to repos.yaml
- [ ] Audit script passes (no kyleos gap)
```

## Troubleshooting

### Audit Script Not Executable
```bash
chmod +x ./scripts/ledger-audit.sh
```

### Pre-Commit Hook Not Running
```bash
chmod +x ./.claude/hooks/pre-commit

# Verify git hooks directory
ls -la .git/hooks/
```

### False Positives

If audit detects gaps that are intentional:
- Archive folders: Keep them outside `~/Desktop/projects/` or add to `.auditignore`
- Notes/scratch work: Don't require ledger documentation for everything

## Related Documentation

- **Ledger Query Skill:** `./.claude/skills/ledger-query/SKILL.md`
- **Issue Execution:** `./.claude/skills/issue-execution/SKILL.md`
- **Repos Schema:** `./ledger/projects/repos.yaml` (see comments)

## Changelog

- 2025-12-16: Initial audit system created (Issue #106)
