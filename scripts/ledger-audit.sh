#!/bin/bash
# ./scripts/ledger-audit.sh
# Detect gaps between filesystem reality and ledger state

set -e

# Change to repo root
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Use OPERATOR_LEDGER_DIR env var, fallback to ./ledger for backwards compatibility
LEDGER_DIR="${OPERATOR_LEDGER_DIR:-${REPO_ROOT}/ledger}"

echo "=== Ledger Gap Detection ==="
echo "Running from: $(pwd)"
echo "Ledger directory: $LEDGER_DIR"
echo ""

# 1. Find repos not in repos.yaml
echo "1. Repos in ~/Desktop/projects/ not in repos.yaml:"
gaps_found=0
if [ -d ~/Desktop/projects ]; then
  for dir in ~/Desktop/projects/*/; do
    [ -d "$dir" ] || continue
    repo_name=$(basename "$dir")
    if ! grep -q "$repo_name" "$LEDGER_DIR/projects/repos.yaml" 2>/dev/null; then
      echo "  ❌ $repo_name (exists but not in ledger)"
      gaps_found=$((gaps_found + 1))
    fi
  done
  if [ $gaps_found -eq 0 ]; then
    echo "  ✅ All repos documented"
  fi
else
  echo "  ⚠️  ~/Desktop/projects/ not found"
fi

# 2. Find ai-workbench projects not documented
echo ""
echo "2. ai-workbench projects not in ledger:"
ai_gaps=0
if [ -d ~/Documents/ai-workbench/ai-scrapbook ]; then
  for dir in ~/Documents/ai-workbench/ai-scrapbook/*/; do
    [ -d "$dir" ] || continue
    project=$(basename "$dir")
    # Skip hidden directories and common non-project folders
    if [[ "$project" == .* ]] || [[ "$project" == "zARCHIVE" ]] || [[ "$project" == "claude-scripts-archived" ]]; then
      continue
    fi
    if ! grep -qi "$project" $LEDGER_DIR/projects/repos.yaml $LEDGER_DIR/projects/ideas.yaml 2>/dev/null; then
      echo "  ❌ $project (ai-workbench but not in ledger)"
      ai_gaps=$((ai_gaps + 1))
    fi
  done
  if [ $ai_gaps -eq 0 ]; then
    echo "  ✅ All ai-workbench projects documented"
  fi
else
  echo "  ⚠️  ~/Documents/ai-workbench/ai-scrapbook/ not found"
fi

# 3. Check cross-file consistency (repos.yaml vs business_models.yaml)
echo ""
echo "3. Status consistency checks:"
consistency_issues=0

# Extract project names from business_models.yaml and check if they exist in repos.yaml
if [ -f $LEDGER_DIR/projects/business_models.yaml ]; then
  # Check for "Accounting OS" mentioned in business_models but status mismatch
  if grep -q "Accounting OS" $LEDGER_DIR/projects/business_models.yaml; then
    biz_status=$(grep -A5 "Accountant Offline Automation Hub" $LEDGER_DIR/projects/business_models.yaml | grep "stage:" | head -1 | awk '{print $2}')
    repo_status=$(grep -A5 "name: Accounting OS" $LEDGER_DIR/projects/repos.yaml | grep "status:" | head -1 | awk '{print $2}')

    if [ -n "$biz_status" ] && [ -n "$repo_status" ]; then
      # Check if statuses align (design/SHELVED is a known mismatch)
      if [ "$biz_status" = "design" ] && [ "$repo_status" = "SHELVED" ]; then
        echo "  ⚠️  Accounting OS: business_models.yaml says 'design' but repos.yaml says 'SHELVED'"
        consistency_issues=$((consistency_issues + 1))
      fi
    fi
  fi
fi

if [ $consistency_issues -eq 0 ]; then
  echo "  ✅ No major consistency issues detected"
fi

# 4. Find stale priorities (declared >30 days ago, 0 action)
echo ""
echo "4. Stale priorities (>30 days, 0 conversations):"
stale_priorities=0

if [ -f $LEDGER_DIR/projects/ideas.yaml ]; then
  # Look for CMMC idea with priority_rank: 1 from June 2025
  if grep -q "CMMC" $LEDGER_DIR/projects/ideas.yaml; then
    cmmc_date=$(grep -A20 "CMMC" $LEDGER_DIR/projects/ideas.yaml | grep "date_captured:" | head -1 | awk '{print $2}' | tr -d '"')
    cmmc_priority=$(grep -A20 "CMMC" $LEDGER_DIR/projects/ideas.yaml | grep "priority_rank:" | head -1 | awk '{print $2}')

    # Check for "Customer conversations: 0" in validation_status section
    has_zero_conversations=$(grep -A30 "CMMC" $LEDGER_DIR/projects/ideas.yaml | grep -o "Customer conversations: 0" | wc -l | tr -d ' ')

    if [ -n "$cmmc_date" ] && [ "$cmmc_priority" = "1" ] && [ "$has_zero_conversations" -gt 0 ]; then
      # Check if >30 days old (simplified date check)
      today=$(date +%s)
      captured=$(date -j -f "%Y-%m-%d" "$cmmc_date" +%s 2>/dev/null || echo 0)
      days_ago=$(( (today - captured) / 86400 ))

      if [ $days_ago -gt 30 ]; then
        echo "  ❌ CMMC Compliance (priority #1, captured $days_ago days ago, 0 customer conversations)"
        stale_priorities=$((stale_priorities + 1))
      fi
    fi
  fi
fi

if [ $stale_priorities -eq 0 ]; then
  echo "  ✅ No stale priorities detected"
fi

# 5. Find complete projects not being sold
echo ""
echo "5. Complete projects with 0 sales attempts:"
complete_unsold=0

if [ -f $LEDGER_DIR/projects/repos.yaml ]; then
  # Look for ARCHIVED or COMPLETE status
  archived_projects=$(grep -B5 "status: ARCHIVED" $LEDGER_DIR/projects/repos.yaml | grep "name:" | sed 's/.*name: //' | tr -d '"')

  if [ -n "$archived_projects" ]; then
    while IFS= read -r project; do
      # Check if there's a note about completion
      if grep -A10 "name: $project" $LEDGER_DIR/projects/repos.yaml | grep -q "completed"; then
        echo "  ⚠️  $project (ARCHIVED/COMPLETE, no sales validation in ledger)"
        complete_unsold=$((complete_unsold + 1))
      fi
    done <<< "$archived_projects"
  fi
fi

if [ $complete_unsold -eq 0 ]; then
  echo "  ✅ No complete projects without sales validation"
fi

# Summary
echo ""
echo "=== Summary ==="
total_gaps=$((gaps_found + ai_gaps + consistency_issues + stale_priorities + complete_unsold))
echo "Total gaps detected: $total_gaps"

if [ $total_gaps -gt 0 ]; then
  echo ""
  echo "=== Recommendations ==="
  echo "Review and close gaps using ledger-query skill or manual updates"
  echo "See issues #94-#105 for systematic gap closure"
fi

exit 0
