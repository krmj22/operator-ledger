# Operator-Ledger Project Instructions

## Project Identity
Personal knowledge and capability management system for capturing CLI agent sessions, tracking skills with evidence-based levels, recording technical decisions, and analyzing activity patterns over time.

**Philosophy**: Filesystem is truth. Simplest solution wins. Fail fast, fail hard. Evidence before opinion.

## Critical Environment Setup

### Required Environment Variables
```bash
# Personal ledger location (private data, external to repo)
export OPERATOR_LEDGER_DIR="$HOME/.operator/ledger"

# Transcript source directory (e.g., ~/.claude, ~/.gemini)
export OPERATOR_DATA_DIR="$HOME/.claude"

# Claude CLI binary (optional, auto-detected)
export CLAUDE_BIN="/opt/homebrew/bin/claude"
```

**CRITICAL**: All scripts use `OPERATOR_LEDGER_DIR` for ledger operations. Never hardcode paths. Use `Path.expanduser()` for tilde expansion in Python scripts.

## Repository Structure

### Public vs Private Separation
- **Public Repo** (`operator-ledger/`): Scripts, tests, templates, documentation
- **Private Data** (`$OPERATOR_LEDGER_DIR`): Personal skills, decisions, sessions, activity logs

This separation enables safe sharing while protecting personal information.

### Key Directories
```
operator-ledger/
├── .ledger-template/        # Setup templates for new ledgers
├── scripts/                 # 39 automation scripts (Python + Bash)
├── packages/                # Core modules (capture, common)
├── tests/                   # Test suite with sample data
└── README.md               # Comprehensive documentation

$OPERATOR_LEDGER_DIR/       # EXTERNAL - never in git
├── operator/               # Identity, philosophy, contacts
├── skills/                 # active.yaml, history.yaml, validated.yaml
├── projects/               # Repos, trajectory, business models
├── decisions/              # Canonical decisions with rationale
├── activity/               # Commits, sessions, status updates
└── _meta/                  # ingestion_history.yaml, metadata
```

## Confidence & Evidence Requirements

### ≥95% Confidence Threshold
- **Never record** uncertain information in ledger
- **Prove problems exist** before proposing solutions
- **Filesystem is truth**: Read files before proposing changes
- **Evidence required**: Test output, git diffs, measurements

### Outcomes
- **SAT**: All criteria met with filesystem proof
- **UNSAT**: Escalate with specific failure analysis
- No partial completion, no "ready for review"

## File & Naming Conventions

### Scripts
- **Action pattern**: `{action}_{subject}.py` (e.g., `generate_dashboard_data.py`)
- **Orchestrators**: Use `.sh` for workflows (e.g., `daily_ingestion.sh`)
- **Tests**: `test_{module}.py`

### Data Formats
- **YAML**: Primary ledger format (skills, decisions, projects)
- **JSON**: Session transcripts (session envelope contract v1.2.0)
- **JSONL**: Claude Code history format

### Session Envelope Contract (v1.2.0)
```json
{
  "schema_version": "1.2.0",
  "session_id": "SHA-256 hash",
  "start_time": "ISO8601",
  "interactions": [
    {
      "id": "str",
      "type": "user_prompt|assistant_response",
      "timestamp": "ISO8601",
      "content": "str"
    }
  ]
}
```

## Code Patterns & Standards

### Python Style
- **Type hints**: Required for function signatures
- **Error handling**: Explicit checks, fail-fast with descriptive errors
- **Path handling**: Use `Path.expanduser()` for tilde support
- **Idempotency**: Scripts safe to run multiple times

### Error Exit Codes
- `0`: Success (SAT)
- `1`: Warnings (UNSAT)
- `2`: Critical violations (hard failure)

### Temporal Metadata
All skill records include:
```yaml
temporal_metadata:
  session_count: 12          # Total sessions using skill
  last_seen: "2026-01-14"    # ISO8601 - most recent use
  frequency: "frequent"      # frequent|occasional|rare
  validation: "consistent"   # consistent|verified|uncertain
```

## Testing Requirements

### Before Any Commit
```bash
# Run temporal gate regression tests
python3 tests/test_temporal_gates.py  # Exit 0 required

# Run full test suite
python3 -m unittest discover tests/
```

### Test Types
- **Unit**: Individual function behavior (e.g., `test_cache_parser.py`)
- **Integration**: End-to-end workflows (e.g., `test_cache_ingestion_smoke.py`)
- **Regression**: Temporal gate violations (e.g., `test_temporal_gates.py`)

### Test Fixtures
Located in `tests/sample_data/`:
- `valid_session.json`: Compliant session envelope
- `cache_session_sample.jsonl`: Claude Code format
- `codex_session_sample.jsonl`: Codex format
- `gemini_session_sample.json`: Gemini format

## Ingestion Pipeline Workflow

### Primary Orchestrator: `daily_ingestion.sh`
```
Step 0: Cache Session Ingestion (monitor_cache_incremental.py)
  ↓
Step 1: Session Activity Tracking (session_tracker.py)
  ↓
Step 2: Skill Ingestion Analysis (skill_ingestion.py)
  ↓
Step 3: Agent-Driven Validation (agent_validate_skills.py)
  ↓
Temporal Gate Regression Tests (blocks on violations)
```

### Supported Cache Formats
1. **Claude Code**: `~/.claude/projects/*.jsonl`
2. **Codex**: JSONL with `session_meta` field
3. **Gemini**: `~/.gemini/tmp/*/chats/session-*.json`

### Deduplication
- Tracked in `$OPERATOR_LEDGER_DIR/_meta/ingestion_history.yaml`
- Records: `session_id`, `source`, `timestamp`, `status`
- Prevents re-ingesting same session from multiple sources

## Skill Management Rules

### Promotion (historical → active)
Automatically promote when ANY of:
- `session_count ≥ 5`
- `3+ sessions in last 30 days`
- `Level 2+ with validated outcome evidence`
- Manual override (`status='active'`)

### Demotion (active → historical)
Automatically demote when ANY of:
- `90+ days inactive` (from `temporal_metadata.last_seen`)
- `Level 0-1 after decay`
- `status='dormant'`
- `session_count ≤ 2 AND Level 2+` (weak evidence)

### Temporal Gates
Block inappropriate skill level changes:
- Level increases require sufficient `session_count` AND recent activity
- Violations trigger exit code 2 in `test_temporal_gates.py`
- See tests for specific thresholds

## Review Flags Pattern (Issue #57)

When flagging skills for human review:
```yaml
review_flags:
  - trigger: "single_session_level_1"      # What caused flag
    severity: "low|medium|high"
    message: "Human-readable explanation"
    added: "2025-01-14"                    # ISO8601 - REQUIRED
    resolved: "2025-01-15"                 # OPTIONAL
    resolution: "What was done"
    resolved_by: "user|agent|auto"        # OPTIONAL
```

## Strategic Patterns (High-Value Skills)

Detected by `skill_ingestion.py` with 3.0x weight multiplier:
- **Framework Design**: CRISP-E, CONSTRAINTS, gates, binary outcomes, SAT/UNSAT
- **Specification Engineering**: PRD, IAW, acceptance criteria, requirement articulation
- **Verification Architecture**: Proof protocols, evidence requirements, test strategies
- **Gray Area Resolution**: Ambiguity handling, competing concerns, trade-off analysis

## Common Workflows

### Initialize New Ledger
```bash
# Copy templates to external ledger location
cp -r .ledger-template/* $OPERATOR_LEDGER_DIR/

# Verify structure
python3 scripts/ledger_verify.py
```

### Daily Ingestion
```bash
# Run full pipeline
./scripts/daily_ingestion.sh

# Review skill ingestion report
cat $OPERATOR_LEDGER_DIR/_meta/skill_ingestion_report.yaml

# Apply if SAT
python3 scripts/apply_skill_updates.py
```

### Query Sessions
```bash
# Last 7 days
python3 scripts/query_sessions.py --last-n-days 7

# Specific status
python3 scripts/query_sessions.py --status completed
```

### Verify Integrity
```bash
# Comprehensive preflight checks
python3 scripts/ledger_verify.py
# Exit 0: SAT (pass)
# Exit 1: UNSAT (fail)
```

## Git Workflow

### Branch Strategy
- `main`: Stable, tested, production-ready
- Feature branches: Use descriptive names (e.g., `fix-temporal-gates`, `add-gemini-support`)

### Commit Standards
- **Prefix**: `fix:`, `feat:`, `test:`, `docs:`, `refactor:`
- **Format**: `<prefix>: <concise description>`
- **Examples**:
  - `fix: ingestion scripts use OPERATOR_LEDGER_DIR with tilde expansion`
  - `feat: add Gemini cache format support`
  - `test: add temporal gate regression tests`

### Pre-Commit Checks
1. Run `python3 tests/test_temporal_gates.py` (exit 0 required)
2. Run `python3 -m unittest discover tests/`
3. Run `python3 scripts/ledger_verify.py` (if testing ledger operations)

## Implementation Language

### During Implementation
- **Declarative statements**: "Implemented X at file:line"
- **NO hedging**: "should/might/probably" forbidden
- **Show evidence**: Include file:line references, test output, git diffs

### During Planning/Brainstorming
- Hedging acceptable when proposing options
- Use when exploring trade-offs or approaches
- Switch to declarative once implementation begins

## Verification Requirements

### Before Claiming Completion
- ✅ All tests pass (exit 0)
- ✅ Temporal gates satisfied
- ✅ Files read before edited
- ✅ Evidence gathered (test output, measurements)
- ✅ Changes verified in filesystem

### UNSAT Escalation
If requirements cannot be met:
1. State specific failure
2. Provide failure analysis
3. Show evidence of what went wrong
4. Propose investigation path

## Documentation Standards

### Code Comments
- Only where logic isn't self-evident
- Avoid over-documenting obvious patterns
- Focus on **why**, not **what**

### Script Docstrings
- Purpose statement
- Environment variables required
- Exit codes
- Example usage

### YAML Comments
- Context for complex structures
- Rationale for non-obvious values
- References to related files/decisions

## Automation Setup (macOS)

### launchd Integration
```bash
# Install periodic cache monitor (runs every 5 min)
./scripts/setup_launchd.sh

# Check status
launchctl list | grep operator

# View logs
tail -f ~/Library/Logs/operator-ledger-cache-monitor.log
```

## Anti-Patterns to Avoid

### ❌ Don't
- Hardcode paths (use `OPERATOR_LEDGER_DIR`)
- Record uncertain information
- Silently fail (use descriptive errors)
- Over-engineer solutions
- Hedge during implementation ("should work")
- Commit private data to git
- Skip temporal gate tests
- Assume without reading files

### ✅ Do
- Use environment variables for all paths
- Require ≥95% confidence before recording
- Fail fast with exit codes
- Choose simplest solution
- Use declarative statements ("Implemented X")
- Keep private data external
- Run regression tests before commit
- Read filesystem before proposing changes

## Key Files Reference

| File | Purpose | Exit Codes |
|------|---------|------------|
| `daily_ingestion.sh` | Main orchestrator | 0, 1 |
| `skill_ingestion.py` | AI-powered skill extraction | 0, 1 |
| `ledger_verify.py` | Integrity checks | 0 (SAT), 1 (UNSAT) |
| `test_temporal_gates.py` | Regression tests | 0 (pass), 1 (warn), 2 (critical) |
| `session_tracker.py` | Session metadata extraction | 0, 1 |
| `manage_skill_status.py` | Auto promotion/demotion | 0, 1 |

## Context for Agents

When working on this codebase:
1. **Read first**: Examine related files and git history
2. **Test coverage**: Changes require corresponding tests
3. **Temporal gates**: Respect skill level progression rules
4. **Evidence-based**: Prove before proposing
5. **Portable**: Use env vars, not hardcoded paths
6. **Idempotent**: Scripts safe to run multiple times
7. **Fail hard**: No silent failures or partial completion

## Recent Focus Areas (Last 5 Commits)

1. Environment variable portability (tilde expansion)
2. OPERATOR_LEDGER_DIR standardization across scripts
3. Temporal gate regression tests
4. Hardcoded path removal
5. Initial framework commit

---

**Last Updated**: 2026-01-14
**Contract Version**: Session Envelope v1.2.0
**Confidence Threshold**: ≥95%
