#!/usr/bin/env python3
"""
Incremental cache monitoring: Process only new cache sessions.

Designed for real-time monitoring (launchd every 5 minutes).
Phase 4 of #83 - Real-time monitoring with deduplication.
"""

import os
import sys
from pathlib import Path
import time
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.capture.cache_parser import parse_cache_session
from packages.capture.deduplication import (
    load_ingestion_history,
    save_ingestion_history,
    is_session_processed,
    mark_session_processed,
    extract_session_id_from_cache
)


def find_new_sessions(cache_dir: Path, since_minutes: int = 10, gemini_cache_dir: Path = None):
    """Find cache files modified in the last N minutes.

    Args:
        cache_dir: Claude Code cache directory
        since_minutes: Look for files modified within this time window
        gemini_cache_dir: Optional Gemini cache directory

    Returns:
        List of recently modified cache files
    """
    cache_files = []
    cutoff_time = datetime.now() - timedelta(minutes=since_minutes)

    # Find Claude Code and Codex sessions (JSONL)
    for cache_file in Path(cache_dir).rglob("*.jsonl"):
        # Check modification time
        try:
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if mtime > cutoff_time:
                cache_files.append(cache_file)
        except Exception:
            continue

    # Find Gemini sessions (JSON)
    if gemini_cache_dir and gemini_cache_dir.exists():
        for cache_file in Path(gemini_cache_dir).rglob("session-*.json"):
            try:
                mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
                if mtime > cutoff_time:
                    cache_files.append(cache_file)
            except Exception:
                continue

    return cache_files


def incremental_ingest(cache_dir: Path, history_file: Path, since_minutes: int = 10, gemini_cache_dir: Path = None):
    """Process only new/recent cache sessions.

    Args:
        cache_dir: Claude Code cache directory
        history_file: Path to ingestion history YAML
        since_minutes: Look for sessions modified within this time window
        gemini_cache_dir: Optional Gemini cache directory
    """

    # Find recently modified files
    new_files = find_new_sessions(cache_dir, since_minutes, gemini_cache_dir)

    if not new_files:
        print(f"No new sessions found in last {since_minutes} minutes")
        return True

    print(f"Found {len(new_files)} recently modified sessions")

    # Load history
    history = load_ingestion_history(history_file)

    # Statistics
    processed = 0
    duplicates = 0
    errors = 0

    start_time = time.time()

    for cache_file in new_files:
        try:
            # Extract session ID
            session_id = extract_session_id_from_cache(cache_file)

            if not session_id:
                errors += 1
                continue

            # Check if already processed
            if is_session_processed(history, session_id):
                duplicates += 1
                continue

            # Parse session for timestamp and project
            parsed = parse_cache_session(cache_file)

            # Mark as processed with metadata for fallback matching
            # Source type is auto-detected by parser (claude-code-cache, codex-cache, or gemini-cache)
            mark_session_processed(
                history,
                session_id,
                parsed.get('source', 'claude-code-cache'),
                str(cache_file),
                timestamp=parsed.get('start_time'),
                project_path=parsed.get('project_path')
            )

            processed += 1
            print(f"  Ingested: {cache_file.name}")

        except Exception as e:
            print(f"  Error: {cache_file.name}: {e}")
            errors += 1

    # Save history if any changes
    if processed > 0:
        save_ingestion_history(history, history_file)

    duration = time.time() - start_time

    # Summary
    print(f"Incremental ingestion complete: {processed} new, {duplicates} duplicates, {errors} errors ({duration:.2f}s)")

    return errors == 0


if __name__ == "__main__":
    cache_dir = Path.home() / ".claude" / "projects"
    gemini_cache_dir = Path.home() / ".gemini" / "tmp"

    # Use OPERATOR_LEDGER_DIR env var, fallback to ./ledger for backwards compatibility
    ledger_dir = Path(os.getenv('OPERATOR_LEDGER_DIR', Path(__file__).parent.parent / 'ledger'))
    history_file = ledger_dir / "_meta" / "ingestion_history.yaml"

    # Check for recent sessions (last 10 minutes by default)
    success = incremental_ingest(cache_dir, history_file, since_minutes=10, gemini_cache_dir=gemini_cache_dir)
    sys.exit(0 if success else 1)
