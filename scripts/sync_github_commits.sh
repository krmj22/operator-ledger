#!/bin/bash
# Orchestrate incremental GitHub commit ingestion pipeline
# Part of #92: Daily automation for commit tracking

set -euo pipefail

# Auto-detect project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEDGER_DIR="${SCRIPT_DIR}/.."
PROJECT_ROOT="${LEDGER_DIR}/../.."
LOGS_DIR="${LEDGER_DIR}/logs"
COMMIT_INDEX="${LEDGER_DIR}/commit_index.yaml"

# Ensure logs directory exists
mkdir -p "${LOGS_DIR}"

# Log start time
START_TIME=$(date +%s)
echo "=== GitHub Commit Sync Started: $(date) ===" | tee "${LOGS_DIR}/github_sync.log"

# Get last sync timestamp from commit_index.yaml
if [ -f "${COMMIT_INDEX}" ]; then
    LAST_SYNC=$(python3 -c "import yaml; data=yaml.safe_load(open('${COMMIT_INDEX}')); print(data.get('indexed_at', '').split('T')[0] if data.get('indexed_at') else '')" 2>/dev/null || echo "")
    echo "Last sync: ${LAST_SYNC:-never}" | tee -a "${LOGS_DIR}/github_sync.log"
else
    LAST_SYNC=""
    echo "No previous index found - performing full sync" | tee -a "${LOGS_DIR}/github_sync.log"
fi

# Incremental fetch (commits since last_sync)
echo "Fetching commits..." | tee -a "${LOGS_DIR}/github_sync.log"
if [ -n "${LAST_SYNC}" ]; then
    python3 "${SCRIPT_DIR}/github_commit_indexer.py" --since "${LAST_SYNC}" 2>&1 | tee -a "${LOGS_DIR}/github_sync.log"
else
    python3 "${SCRIPT_DIR}/github_commit_indexer.py" 2>&1 | tee -a "${LOGS_DIR}/github_sync.log"
fi

# Extract evidence and decisions
echo "Extracting evidence..." | tee -a "${LOGS_DIR}/github_sync.log"
python3 "${SCRIPT_DIR}/extract_commit_evidence.py" 2>&1 | tee -a "${LOGS_DIR}/github_sync.log"

# Generate summaries
echo "Generating summaries..." | tee -a "${LOGS_DIR}/github_sync.log"
python3 "${SCRIPT_DIR}/generate_commit_summary.py" 2>&1 | tee -a "${LOGS_DIR}/github_sync.log"

# Decision recency tracking
echo "Updating decision recency..." | tee -a "${LOGS_DIR}/github_sync.log"
python3 "${SCRIPT_DIR}/update_decision_recency.py" 2>&1 | tee -a "${LOGS_DIR}/github_sync.log"

# Calculate runtime
END_TIME=$(date +%s)
RUNTIME=$((END_TIME - START_TIME))
echo "=== Sync Complete: $(date) ===" | tee -a "${LOGS_DIR}/github_sync.log"
echo "Runtime: ${RUNTIME}s" | tee -a "${LOGS_DIR}/github_sync.log"

if [ ${RUNTIME} -ge 60 ]; then
    echo "WARNING: Runtime exceeded 60s threshold" | tee -a "${LOGS_DIR}/github_sync.log"
fi
