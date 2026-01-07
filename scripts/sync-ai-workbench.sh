#!/bin/bash
# ./scripts/sync-ai-workbench.sh
# Detect new work in ai-workbench and prompt for ledger entry

set -e

# Change to repo root
cd "$(dirname "$0")/.."

echo "=== AI Workbench → Ledger Sync ==="
echo "Scanning ai-workbench for undocumented work..."
echo ""

# Check if ai-workbench exists
if [ ! -d ~/Documents/ai-workbench/ai-scrapbook ]; then
  echo "⚠️  ~/Documents/ai-workbench/ai-scrapbook/ not found"
  exit 0
fi

# Find directories modified in last 7 days
undocumented=0

echo "Projects modified in last 7 days:"
find ~/Documents/ai-workbench/ai-scrapbook/ -type d -maxdepth 1 -mtime -7 2>/dev/null | while read dir; do
  # Skip the root directory
  [ "$dir" = ~/Documents/ai-workbench/ai-scrapbook/ ] && continue

  project=$(basename "$dir")

  # Skip hidden directories and archive folders
  if [[ "$project" == .* ]] || [[ "$project" == "zARCHIVE" ]] || [[ "$project" == "claude-scripts-archived" ]]; then
    continue
  fi

  # Check if documented in ledger
  if ! grep -qi "$project" ./ledger/projects/repos.yaml ./ledger/projects/ideas.yaml 2>/dev/null; then
    echo "  📁 $project"
    echo "     Modified: $(stat -f "%Sm" -t "%Y-%m-%d" "$dir")"
    echo "     ❌ Not found in ledger"
    echo "     Should this be in repos.yaml or ideas.yaml?"
    echo ""
    undocumented=$((undocumented + 1))
  fi
done

if [ $undocumented -eq 0 ]; then
  echo "✅ All recent ai-workbench projects are documented in ledger"
else
  echo "=== Action Required ==="
  echo "Consider adding undocumented projects to:"
  echo "  - ./ledger/projects/repos.yaml (if it's a repo/codebase)"
  echo "  - ./ledger/projects/ideas.yaml (if it's a business idea)"
fi

exit 0
