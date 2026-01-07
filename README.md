# Operator

Personal knowledge system for tracking skills, projects, and decisions via AI agent sessions.

## What It Does

1. **Captures** CLI agent sessions (Claude Code, etc.)
2. **Tracks** skills with evidence and temporal decay
3. **Records** decisions and their rationale
4. **Analyzes** patterns over time

## Structure

```
operator-ledger/          # PUBLIC REPO
├── .ledger-template/     # Template for personal ledger setup
├── scripts/              # All automation (34+ scripts)
├── tests/                # Test suite
├── packages/             # Package dependencies
└── analysis/             # Analysis and dashboard generation

~/.operator/ledger/       # YOUR PRIVATE DATA (set via OPERATOR_LEDGER_DIR)
├── operator/             # Identity, philosophy, contacts, clinical notes
├── skills/               # Active and historical skills
├── projects/             # Repos, trajectory, business models
├── decisions/            # Canonical and extracted decisions
├── activity/             # Commits, sessions, status
├── logs/                 # Temporal analysis
├── research/             # Research notes and findings
├── docs/                 # Documentation
└── _meta/                # Metadata and system files
```

## Quick Start

```bash
# 1. Set up your personal ledger (one-time setup)
export OPERATOR_LEDGER_DIR="$HOME/.operator/ledger"
bash scripts/setup_ledger.sh

# 2. Set transcript directory (typically ~/.claude for Claude Code)
export OPERATOR_DATA_DIR="$HOME/.claude"

# 3. Add to your shell profile for persistence
echo 'export OPERATOR_LEDGER_DIR="$HOME/.operator/ledger"' >> ~/.bashrc
echo 'export OPERATOR_DATA_DIR="$HOME/.claude"' >> ~/.bashrc

# 4. Run smoke test
bash scripts/smoke_test.sh

# 5. Daily ingestion (processes history.jsonl + cache sessions)
bash scripts/daily_ingestion.sh

# 6. Query recent sessions
python3 scripts/query_sessions.py --last-n-days 7
```

## Environment Variables

- **`OPERATOR_LEDGER_DIR`**: Directory for your personal ledger data (default: `./ledger`)
  - **IMPORTANT**: Set this to keep your personal data separate from the public repo
  - Recommended: `$HOME/.operator/ledger`

- **`OPERATOR_DATA_DIR`**: Directory for transcript data (required)
  - For Claude Code: `$HOME/.claude`
  - For Gemini: `$HOME/.gemini`

### Ingestion Workflow

The operator system **automatically captures** sessions from:
- `~/.claude/history.jsonl` (Claude Code session history)
- `~/.claude/projects/` (Claude Code cache sessions)
- `~/.gemini/tmp/` (Gemini cache sessions, if present)

**Manual transcript exports are deprecated.** The auto-capture workflow replaces the need for manual `.txt` exports. If you have accumulated transcript files from manual exports, they can be safely archived or deleted - the operator system has already captured these sessions from `history.jsonl`.

**Ingestion tracking:** Check ingestion status in:
- `./ledger/_meta/ingestion_history.yaml` - full session ingestion log
- `./ledger/logs/ingestion_*.log` - detailed run logs with timestamps

## Core Principles

- **Filesystem is truth** - All state visible and version-controlled
- **>95% confidence** - Only record what we're certain about
- **Idempotent** - Safe to run multiple times
- **Fail hard** - No silent failures

See `ledger/operator/philosophy.yaml` for full ethos.

## Key Commands

| Task | Command |
|------|---------|
| Ingest sessions | `bash scripts/daily_ingestion.sh` |
| Weekly review | `bash scripts/weekly_temporal_review.sh` |
| Verify ledger | `python3 scripts/ledger_verify.py` |
| Query sessions | `python3 scripts/query_sessions.py --last-n-days 7` |
| Check skill status | `python3 scripts/manage_skill_status.py` |

## Automation

Cache monitoring runs every 5 minutes via launchd:
```bash
bash scripts/setup_launchd.sh install   # Setup
bash scripts/setup_launchd.sh status    # Check
bash scripts/setup_launchd.sh uninstall # Remove
```

## For AI Agents

### Your Role
You are a **maintainer and researcher** for this ledger system. Your job is to:
- Preserve system integrity and enforce >95% confidence threshold
- Gather evidence before proposing changes
- Respect "filesystem is truth" and "simplest solution wins"
- Read before editing, prove before proposing

### Onboarding Sequence

**ALWAYS start here when opening this repo:**

1. **Understand the system**
   ```bash
   # Read the philosophy first
   cat ledger/operator/philosophy.yaml

   # Check current focus
   cat ledger/activity/status.yaml

   # Understand the structure
   cat README.md
   ```

2. **Before proposing ANY change:**
   ```bash
   # Check git history for context
   git log --oneline --grep="keyword" -20
   git log --all --full-history -- path/to/file

   # Search existing files
   grep -r "concept" ledger/

   # Look for related issues/decisions
   gh issue list --search "keyword"
   cat ledger/decisions/canonical.yaml
   ```

3. **Gather evidence**
   - Has this problem caused actual issues? (git log, issue history)
   - Do simpler solutions exist? (grep existing files)
   - Is there prior art? (git blame, commit messages)
   - What's the >95% confidence proof?

### Navigation Guide

| Path | Purpose | When to Check |
|------|---------|---------------|
| `ledger/decisions/canonical.yaml` | Major strategic decisions with full rationale | Before proposing architectural changes |
| `ledger/operator/philosophy.yaml` | Operating principles and ethos | First thing you read |
| `ledger/activity/status.yaml` | Current focus and priorities | When unclear about priorities |
| `ledger/activity/commits/` | Evidence of work done (commit logs) | When researching skill evidence |
| `ledger/skills/` | Skill tracking with temporal decay | When assessing capabilities |
| `ledger/projects/` | Project trajectory and business models | When understanding project context |
| `git log` | The "why" behind implementations | **Always check before proposing changes** |

### Common Patterns

**Researching a topic:**
```bash
# 1. Check git history first
git log --all --grep="topic" --oneline -20

# 2. Search ledger files
grep -r "topic" ledger/

# 3. Check issues and PRs
gh issue list --search "topic"
gh pr list --search "topic" --state all
```

**Before proposing infrastructure:**
```bash
# 1. Prove the problem exists
git log --grep="problem" --oneline -50  # Any evidence of this pain?
gh issue list --search "problem"         # Has this been discussed?

# 2. Check for simpler solutions
grep -r "similar feature" ledger/        # Already solved differently?
git log -- path/to/similar/feature       # How was it done before?

# 3. Gather evidence
# Find 3+ concrete examples where current approach failed
```

### Decision-Making Protocol

1. **Read philosophy.yaml** - Understand "simplest solution wins", ">95% confidence", "evidence over opinion"
2. **Check git history** - Has this been tried? Discussed? Rejected?
3. **Search existing files** - Does a solution already exist?
4. **Gather evidence** - Can you prove the problem with concrete examples?
5. **Propose minimally** - Smallest change that solves the proven problem

### Red Flags (Don't Do This)

❌ Proposing changes without reading existing files
❌ Suggesting infrastructure without evidence of problems
❌ Filing issues without checking git history
❌ Adding complexity without proving simpler solutions inadequate
❌ Using hedging language during implementation ("should", "might", "probably")
❌ Claiming completion without filesystem proof

### Git History is Your Best Tool

The git log contains the "why" behind every decision:
```bash
# Why does this file exist?
git log --follow -- path/to/file

# When was this decision made?
git log --all --grep="decision keyword" --oneline

# What changed recently?
git log --since="2 weeks ago" --oneline

# Who worked on this area?
git log --author="name" -- path/
```

**Use git history liberally.** It prevents proposing solutions to already-solved problems.

## Status

Active development. See GitHub Issues for roadmap.
