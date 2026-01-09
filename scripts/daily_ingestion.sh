#!/bin/bash

# Daily Transcript Ingestion Script
# Runs Claude Code in non-interactive mode to analyze new transcripts
# and update operator ledger YAMLs

set -euo pipefail

# Configuration - use script location to find operator repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Use OPERATOR_DATA_DIR env var if set, otherwise fail with clear error
TRANSCRIPT_DIR="${OPERATOR_DATA_DIR}"
# Expand tilde to home directory
TRANSCRIPT_DIR="${TRANSCRIPT_DIR/#\~/$HOME}"

# Use OPERATOR_LEDGER_DIR env var, fallback to ./ledger for backwards compatibility
LEDGER_DIR="${OPERATOR_LEDGER_DIR:-${REPO_ROOT}/ledger}"
# Expand tilde to home directory
LEDGER_DIR="${LEDGER_DIR/#\~/$HOME}"
LOG_DIR="${LEDGER_DIR}/logs"
LOG_FILE="${LOG_DIR}/ingestion_$(date +%Y%m%d_%H%M%S).log"
CLAUDE_BIN="/opt/homebrew/bin/claude"

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Change to repo root directory
cd "${REPO_ROOT}"

# Log start
echo "=== Transcript Ingestion Started: $(date) ===" | tee -a "${LOG_FILE}"
echo "Transcript source: ${TRANSCRIPT_DIR}" | tee -a "${LOG_FILE}"
echo "" | tee -a "${LOG_FILE}"

# Step 0: Ingest new cache sessions (Issue #83)
echo "=== Step 0: Cache Session Ingestion ===" | tee -a "${LOG_FILE}"
python3 "${REPO_ROOT}/scripts/monitor_cache_incremental.py" 2>&1 | tee -a "${LOG_FILE}" || true
CACHE_INGEST_EXIT=${PIPESTATUS[0]}
echo "" | tee -a "${LOG_FILE}"

if [ ${CACHE_INGEST_EXIT} -ne 0 ]; then
    echo "⚠️  Cache ingestion completed with warnings (exit code: ${CACHE_INGEST_EXIT})" | tee -a "${LOG_FILE}"
    echo "" | tee -a "${LOG_FILE}"
fi

# Step 1: Track session activity (Issue #45)
echo "=== Step 1: Tracking Session Activity ===" | tee -a "${LOG_FILE}"
python3 "${SCRIPT_DIR}/session_tracker.py" --transcript-dir "${TRANSCRIPT_DIR}" 2>&1 | tee -a "${LOG_FILE}" || true
SESSION_TRACK_EXIT=${PIPESTATUS[0]}
echo "" | tee -a "${LOG_FILE}"

if [ ${SESSION_TRACK_EXIT} -ne 0 ]; then
    echo "⚠️  Session tracking completed with warnings (exit code: ${SESSION_TRACK_EXIT})" | tee -a "${LOG_FILE}"
    echo "Proceeding with skill ingestion..." | tee -a "${LOG_FILE}"
    echo "" | tee -a "${LOG_FILE}"
fi

# Step 2: Run skill ingestion analysis (Issue #44 - No auto-apply)
echo "=== Step 2: Running Skill Ingestion Analysis ===" | tee -a "${LOG_FILE}"
python3 "${SCRIPT_DIR}/skill_ingestion.py" \
  --transcript-dir "${TRANSCRIPT_DIR}" \
  --skills-file "${LEDGER_DIR}/skills.yaml" \
  --output "${LEDGER_DIR}/skill_ingestion_report.yaml" \
  2>&1 | tee -a "${LOG_FILE}"

# Capture exit code
EXIT_CODE=${PIPESTATUS[0]}

echo "" | tee -a "${LOG_FILE}"
if [ ${EXIT_CODE} -eq 0 ]; then
    echo "✅ Skill analysis complete - report generated" | tee -a "${LOG_FILE}"
    echo "⚠️  Review and approve updates before applying (see report for instructions)" | tee -a "${LOG_FILE}"
else
    echo "❌ Skill analysis failed with exit code: ${EXIT_CODE}" | tee -a "${LOG_FILE}"
fi

# Step 3: Agent-driven skill validation (Issue #69)
if [ ${EXIT_CODE} -eq 0 ]; then
    echo "" | tee -a "${LOG_FILE}"
    echo "=== Step 3: Agent-Driven Skill Validation ===" | tee -a "${LOG_FILE}"
    python3 "${SCRIPT_DIR}/agent_validate_skills.py" 2>&1 | tee -a "${LOG_FILE}" || true
    VALIDATION_EXIT=${PIPESTATUS[0]}
    echo "" | tee -a "${LOG_FILE}"

    if [ ${VALIDATION_EXIT} -ne 0 ]; then
        echo "⚠️  Agent validation completed with warnings (exit code: ${VALIDATION_EXIT})" | tee -a "${LOG_FILE}"
    else
        echo "✅ Agent validation complete - audit report generated" | tee -a "${LOG_FILE}"
    fi
fi

# Log completion
echo "" | tee -a "${LOG_FILE}"
echo "=== Transcript Ingestion Completed: $(date) ===" | tee -a "${LOG_FILE}"
echo "Exit code: ${EXIT_CODE}" | tee -a "${LOG_FILE}"

# Run temporal gate regression tests
if [ ${EXIT_CODE} -eq 0 ]; then
    echo "" | tee -a "${LOG_FILE}"
    echo "=== Running Temporal Gate Regression Tests ===" | tee -a "${LOG_FILE}"
    echo "" | tee -a "${LOG_FILE}"

    python3 "${REPO_ROOT}/tests/test_temporal_gates.py" 2>&1 | tee -a "${LOG_FILE}"
    TEST_EXIT=${PIPESTATUS[0]}

    echo "" | tee -a "${LOG_FILE}"

    if [ $TEST_EXIT -eq 2 ]; then
        echo "❌ CRITICAL: Temporal gate violations detected!" | tee -a "${LOG_FILE}"
        echo "Review ${LOG_FILE} for details" | tee -a "${LOG_FILE}"
        exit 2
    elif [ $TEST_EXIT -eq 1 ]; then
        echo "⚠️  Tests passed with warnings - review recommended" | tee -a "${LOG_FILE}"
    else
        echo "✅ All temporal gate tests passed" | tee -a "${LOG_FILE}"
    fi
fi

exit ${EXIT_CODE}
