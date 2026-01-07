#!/bin/bash
#
# Batch Historical Ingestion: Process all Claude Code cache sessions + manual transcripts
#
# Usage:
#   ./scripts/ingest_cache_batch.sh [--dry-run]
#
# Features:
#   - Deduplication via ingestion_history.yaml
#   - Processes cache JSONL files from ~/.claude/projects/
#   - Processes manual transcripts from JSON Transcription/ui/output/
#   - Idempotent (re-run = 0 new entries if all processed)
#   - Progress reporting
#

set -euo pipefail

# Parse arguments
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "DRY RUN MODE: No files will be modified"
fi

# Paths
CACHE_DIR="$HOME/.claude/projects"
MANUAL_TRANSCRIPT_DIR="$HOME/Desktop/projects/JSON Transcription/ui/output"
HISTORY_FILE="/Users/kylejensen/Desktop/operator/ledger/ingestion_history.yaml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAPTURE_DIR="${SCRIPT_DIR}/../packages/capture"

# Initialize history file if doesn't exist
if [[ ! -f "$HISTORY_FILE" ]] && [[ "$DRY_RUN" == "false" ]]; then
    mkdir -p "$(dirname "$HISTORY_FILE")"
    echo "processed_sessions: []" > "$HISTORY_FILE"
    echo "Initialized $HISTORY_FILE"
fi

# Count sessions
echo "Scanning for sessions..."
CACHE_COUNT=$(find "$CACHE_DIR" -name "*.jsonl" 2>/dev/null | wc -l | tr -d ' ')
MANUAL_COUNT=$(find "$MANUAL_TRANSCRIPT_DIR" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
TOTAL_FOUND=$((CACHE_COUNT + MANUAL_COUNT))

echo "Found:"
echo "  - Cache sessions: $CACHE_COUNT"
echo "  - Manual transcripts: $MANUAL_COUNT"
echo "  - Total: $TOTAL_FOUND"
echo ""

# Statistics
PROCESSED=0
DUPLICATES=0
ERRORS=0

# Process cache sessions
echo "Processing cache sessions..."
if [[ $CACHE_COUNT -gt 0 ]]; then
    while IFS= read -r cache_file; do
        # Extract session_id
        SESSION_ID=$(python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '${SCRIPT_DIR}/..')
from packages.capture.deduplication import extract_session_id_from_cache
print(extract_session_id_from_cache(Path('$cache_file')))
" 2>/dev/null || echo "")

        if [[ -z "$SESSION_ID" ]]; then
            echo "WARNING: Could not extract session_id from $cache_file"
            ((ERRORS++))
            continue
        fi

        # Check if already processed
        IS_DUPLICATE=$(python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '${SCRIPT_DIR}/..')
from packages.capture.deduplication import load_ingestion_history, is_session_processed
history = load_ingestion_history(Path('$HISTORY_FILE'))
print('true' if is_session_processed(history, '$SESSION_ID') else 'false')
" 2>/dev/null || echo "false")

        if [[ "$IS_DUPLICATE" == "true" ]]; then
            ((DUPLICATES++))
            continue
        fi

        # Process session (unless dry-run)
        if [[ "$DRY_RUN" == "false" ]]; then
            python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '${SCRIPT_DIR}/..')
from packages.capture.deduplication import load_ingestion_history, mark_session_processed, save_ingestion_history
history = load_ingestion_history(Path('$HISTORY_FILE'))
mark_session_processed(history, '$SESSION_ID', 'claude-code-cache', '$cache_file')
save_ingestion_history(history, Path('$HISTORY_FILE'))
" 2>/dev/null || {
                echo "ERROR: Failed to process $cache_file"
                ((ERRORS++))
                continue
            }
        fi

        ((PROCESSED++))

        # Progress reporting every 50 sessions
        if (( PROCESSED % 50 == 0 )); then
            echo "  Processed: $PROCESSED, Duplicates: $DUPLICATES, Errors: $ERRORS"
        fi
    done < <(find "$CACHE_DIR" -name "*.jsonl" 2>/dev/null)
fi

# Process manual transcripts
echo "Processing manual transcripts..."
if [[ $MANUAL_COUNT -gt 0 ]]; then
    while IFS= read -r transcript_file; do
        # Extract session_id
        SESSION_ID=$(python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '${SCRIPT_DIR}/..')
from packages.capture.deduplication import extract_session_id_from_manual_transcript
print(extract_session_id_from_manual_transcript(Path('$transcript_file')))
" 2>/dev/null || echo "")

        if [[ -z "$SESSION_ID" ]]; then
            echo "WARNING: Could not extract session_id from $transcript_file"
            ((ERRORS++))
            continue
        fi

        # Check if already processed
        IS_DUPLICATE=$(python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '${SCRIPT_DIR}/..')
from packages.capture.deduplication import load_ingestion_history, is_session_processed
history = load_ingestion_history(Path('$HISTORY_FILE'))
print('true' if is_session_processed(history, '$SESSION_ID') else 'false')
" 2>/dev/null || echo "false")

        if [[ "$IS_DUPLICATE" == "true" ]]; then
            ((DUPLICATES++))
            continue
        fi

        # Process session (unless dry-run)
        if [[ "$DRY_RUN" == "false" ]]; then
            python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '${SCRIPT_DIR}/..')
from packages.capture.deduplication import load_ingestion_history, mark_session_processed, save_ingestion_history
history = load_ingestion_history(Path('$HISTORY_FILE'))
mark_session_processed(history, '$SESSION_ID', 'manual-transcript', '$transcript_file')
save_ingestion_history(history, Path('$HISTORY_FILE'))
" 2>/dev/null || {
                echo "ERROR: Failed to process $transcript_file"
                ((ERRORS++))
                continue
            }
        fi

        ((PROCESSED++))

        # Progress reporting every 50 sessions
        if (( PROCESSED % 50 == 0 )); then
            echo "  Processed: $PROCESSED, Duplicates: $DUPLICATES, Errors: $ERRORS"
        fi
    done < <(find "$MANUAL_TRANSCRIPT_DIR" -name "*.json" 2>/dev/null)
fi

# Final summary
echo ""
echo "========================================="
echo "Batch Ingestion Complete"
echo "========================================="
echo "Total sessions found: $TOTAL_FOUND"
echo "Newly processed: $PROCESSED"
echo "Duplicates skipped: $DUPLICATES"
echo "Errors: $ERRORS"

if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    echo "DRY RUN: No changes were made"
fi

echo ""
echo "History file: $HISTORY_FILE"

# Exit with error if any failures
if [[ $ERRORS -gt 0 ]]; then
    exit 1
fi
