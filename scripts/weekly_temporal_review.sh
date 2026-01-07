#!/bin/bash
#
# Weekly Temporal Review - Automated Skills Robustness Check
#
# Runs every Sunday at 9:00 AM to:
# 1. Analyze temporal metadata for all skills
# 2. Flag skills violating temporal gates
# 3. Generate review report with recommended actions
# 4. Update health dashboard
#
# Usage: ./scripts/weekly_temporal_review.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEDGER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$LEDGER_DIR/ledger/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/temporal_review_$TIMESTAMP.log"

# Color output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

echo "============================================================" | tee "$LOG_FILE"
echo "Weekly Temporal Skills Review" | tee -a "$LOG_FILE"
echo "$(date)" | tee -a "$LOG_FILE"
echo "============================================================" | tee -a "$LOG_FILE"

log "Starting temporal analysis..."

# Run temporal analysis script
cd "$LEDGER_DIR"
python3 "$LEDGER_DIR/ledger/scripts/analyze_skill_temporal.py" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    success "Temporal analysis complete"
else
    error "Temporal analysis failed - check log for details"
    exit 1
fi

# Run skill status management (promotion/demotion)
log "Reviewing skill status for promotion/demotion..."
python3 "$LEDGER_DIR/scripts/manage_skill_status.py" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    success "Skill status management complete"
else
    error "Skill status management failed - check log for details"
    exit 1
fi

# Synchronize timestamps across ledger files (IAW Issue #53)
log "Synchronizing timestamps across ledger files..."
python3 "$LEDGER_DIR/scripts/sync_timestamps.py" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    success "Timestamp synchronization complete"
else
    warn "Timestamp synchronization failed - check log for details"
    # Non-fatal - continue with review
fi

# Generate review_flags enforcement report (IAW Issue #57)
log "Generating review_flags enforcement report..."
python3 "$LEDGER_DIR/ledger/scripts/generate_review_flags_report.py" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    success "Review flags report generated"
else
    warn "Review flags report generation failed - check log for details"
    # Non-fatal - continue with review
fi

# Load analysis results
ANALYSIS_FILE="$LOG_DIR/temporal_analysis_$(date +%Y%m%d).yaml"

if [ ! -f "$ANALYSIS_FILE" ]; then
    error "Analysis file not found: $ANALYSIS_FILE"
    exit 1
fi

log "Analyzing results for violations..."

# Extract high-severity flags (using Python for YAML parsing)
python3 <<EOF | tee -a "$LOG_FILE"
import yaml
import sys

with open("$ANALYSIS_FILE", 'r') as f:
    data = yaml.safe_load(f)

summary = data.get('summary', {})
skills = data.get('skills', [])

print("\n" + "="*60)
print("TEMPORAL REVIEW SUMMARY")
print("="*60)
print(f"\nTotal skills: {summary.get('total_skills', 0)}")
print(f"\nFrequency distribution:")
for freq, count in summary.get('by_frequency', {}).items():
    print(f"  {freq}: {count}")

print(f"\nConfidence distribution:")
for quality, count in summary.get('by_confidence', {}).items():
    print(f"  {quality}: {count}")

print(f"\nReview flags:")
print(f"  Total: {summary.get('total_review_flags', 0)}")
print(f"  High severity: {summary.get('high_severity_flags', 0)}")

# Skill decay/restoration summary
decay_summary = data.get('decay_summary', {})
if decay_summary:
    print(f"\nSkill decay/restoration:")
    print(f"  Skills restored: {decay_summary.get('restoration_count', 0)}")
    print(f"  Skills decayed: {decay_summary.get('decay_count', 0)}")

# High-severity violations
print("\n" + "="*60)
print("HIGH-SEVERITY VIOLATIONS")
print("="*60)

violations = []
for skill_data in skills:
    high_flags = [f for f in skill_data.get('review_flags', []) if f.get('severity') == 'high']
    if high_flags:
        violations.append({
            'skill': skill_data['skill'],
            'level': skill_data['current_level'],
            'flags': high_flags
        })

if violations:
    for v in violations:
        print(f"\n{v['skill']} (Level {v['level']}):")
        for flag in v['flags']:
            print(f"  ⚠️  {flag['message']}")
else:
    print("\n✅ No high-severity violations detected")

# Stale skills check
print("\n" + "="*60)
print("STALE SKILLS (180+ days)")
print("="*60)

stale_count = summary.get('by_trend', {}).get('stale', 0)
if stale_count > 0:
    stale_skills = [s for s in skills if s['temporal_metadata']['trend'] == 'stale']
    for skill_data in stale_skills:
        print(f"  • {skill_data['skill']} - Last seen: {skill_data['temporal_metadata']['last_seen']}")
else:
    print("\n✅ No stale skills detected")

# Weak confidence skills
print("\n" + "="*60)
print("WEAK CONFIDENCE SKILLS (score < 50)")
print("="*60)

weak_skills = [s for s in skills if s['confidence_metadata']['confidence_score'] < 50]
if weak_skills:
    for skill_data in weak_skills:
        score = skill_data['confidence_metadata']['confidence_score']
        print(f"  • {skill_data['skill']} - Score: {score}")
else:
    print("\n✅ No weak confidence skills detected")

# Decayed skills report
print("\n" + "="*60)
print("SKILL DECAY ACTIONS")
print("="*60)

decay_summary = data.get('decay_summary', {})
decayed_skills = decay_summary.get('decayed_skills', [])
restored_skills = decay_summary.get('restored_skills', [])

if restored_skills:
    print("\n🔄 Skills Restored (reused after decay):")
    for restore in restored_skills:
        print(f"  • {restore['skill']} - Level {restore['old_level']} → Level {restore['new_level']}")
else:
    print("\n  No skills restored this cycle")

if decayed_skills:
    print("\n⬇️  Skills Decayed (inactive):")
    for decay in decayed_skills:
        print(f"  • {decay['skill']} - Level {decay['old_level']} → Level {decay['new_level']} ({decay['recency_days']} days inactive)")
else:
    print("\n  No skills decayed this cycle")

print("\n" + "="*60)

# Exit with appropriate code
if violations or stale_count > 0:
    sys.exit(2)  # Issues found
else:
    sys.exit(0)  # All clear

EOF

ANALYSIS_EXIT_CODE=$?

# Generate recommendations
log "Generating recommendations..."

if [ $ANALYSIS_EXIT_CODE -eq 2 ]; then
    warn "Issues detected - review required"

    # Create action items file
    ACTION_FILE="$LOG_DIR/temporal_actions_$(date +%Y%m%d).md"

    cat > "$ACTION_FILE" <<'ACTIONS'
# Temporal Review Action Items
**Generated:** $(date)

## Recommended Actions

### High-Severity Violations
Skills at Level 2+ with single-session frequency should be downgraded to Level 1.

**Action:** Review each flagged skill and either:
1. Downgrade to Level 1 if truly single-session
2. Verify session_count is accurate (may be detection issue)

### Stale Skills
Skills not used in 180+ days should be reviewed for removal or archival.

**Action:** For each stale skill, decide:
1. Remove if no longer relevant
2. Mark as "archived" if historical but not current
3. Keep if still conceptually valid (Level 0)

### Weak Confidence Skills
Skills with confidence score < 50 need evidence strengthening.

**Action:** Add more evidence or downgrade rating.

---

**Next Review:** $(date -v+7d +%Y-%m-%d)
ACTIONS

    log "Action items created: $ACTION_FILE"

else
    success "No issues detected - all skills pass temporal gates"
fi

# Update health dashboard
log "Updating skill health dashboard..."

DASHBOARD_FILE="$LOG_DIR/system_logs/skill_health_dashboard.md"

python3 <<EOF > "$DASHBOARD_FILE"
import yaml
from datetime import datetime

with open("$ANALYSIS_FILE", 'r') as f:
    data = yaml.safe_load(f)

summary = data.get('summary', {})

print("# Skill Health Dashboard")
print(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"**Analysis Date:** {data.get('analysis_date', 'Unknown')}")
print("\n---\n")

print("## Overall Health")
print(f"- **Total Skills:** {summary.get('total_skills', 0)}")
print(f"- **Review Flags:** {summary.get('total_review_flags', 0)} ({summary.get('high_severity_flags', 0)} high severity)")

# Health status
high_sev = summary.get('high_severity_flags', 0)
if high_sev == 0:
    status = "✅ HEALTHY"
elif high_sev <= 2:
    status = "⚠️  NEEDS ATTENTION"
else:
    status = "❌ CRITICAL"

print(f"- **Status:** {status}")

# Decay/restoration stats
decay_summary = data.get('decay_summary', {})
if decay_summary:
    restored = decay_summary.get('restoration_count', 0)
    decayed = decay_summary.get('decay_count', 0)
    print(f"- **Skills Restored:** {restored}")
    print(f"- **Skills Decayed:** {decayed}")

print()

print("## Frequency Distribution")
for freq, count in summary.get('by_frequency', {}).items():
    pct = round(count / summary.get('total_skills', 1) * 100)
    bar = "█" * (pct // 5)
    print(f"- **{freq}:** {count} ({pct}%) {bar}")

print("\n## Confidence Distribution")
for quality, count in summary.get('by_confidence', {}).items():
    pct = round(count / summary.get('total_skills', 1) * 100)
    bar = "█" * (pct // 5)
    print(f"- **{quality}:** {count} ({pct}%) {bar}")

print("\n## Trend Distribution")
for trend, count in summary.get('by_trend', {}).items():
    pct = round(count / summary.get('total_skills', 1) * 100)
    bar = "█" * (pct // 5)
    print(f"- **{trend}:** {count} ({pct}%) {bar}")

print("\n---\n")
print("**Next Review:** 7 days from last analysis")
EOF

success "Health dashboard updated: $DASHBOARD_FILE"

# Summary
echo "" | tee -a "$LOG_FILE"
echo "============================================================" | tee -a "$LOG_FILE"
echo "REVIEW COMPLETE" | tee -a "$LOG_FILE"
echo "============================================================" | tee -a "$LOG_FILE"
log "Full report: $LOG_FILE"
log "Analysis data: $ANALYSIS_FILE"
if [ $ANALYSIS_EXIT_CODE -eq 2 ]; then
    log "Action items: $LOG_DIR/temporal_actions_$(date +%Y%m%d).md"
fi
log "Health dashboard: $DASHBOARD_FILE"

exit $ANALYSIS_EXIT_CODE
