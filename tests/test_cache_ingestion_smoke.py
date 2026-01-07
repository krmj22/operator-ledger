"""
Smoke tests for cache ingestion system.

Validates end-to-end cache ingestion workflow including:
- Cache parsing
- Deduplication
- Batch ingestion
- Incremental monitoring
"""

import pytest
from pathlib import Path
import tempfile
import yaml
import json


def test_cache_parser_smoke():
    """Smoke test: Cache parser handles real session file."""
    from packages.capture.cache_parser import parse_cache_session

    # Use existing sample data
    cache_file = Path(__file__).parent / "sample_data" / "cache_session_sample.jsonl"

    result = parse_cache_session(cache_file)

    # Verify required fields
    assert result["session_id"] == "0272f9fa-881c-4c28-9feb-46b17c8741f7"
    assert result["summary"] != ""
    assert result["start_time"] is not None
    assert result["source"] == "claude-code-cache"


def test_deduplication_workflow_smoke():
    """Smoke test: Full deduplication workflow prevents duplicates."""
    from packages.capture.deduplication import (
        load_ingestion_history,
        save_ingestion_history,
        is_session_processed,
        mark_session_processed
    )

    # Use temp file for history
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        history_file = Path(f.name)

    try:
        # Load empty history
        history = load_ingestion_history(history_file)
        assert history == {"processed_sessions": []}

        # Mark session as processed
        mark_session_processed(
            history,
            session_id="test-smoke-123",
            source="claude-code-cache",
            source_path="/tmp/test.jsonl",
            timestamp="2025-12-13T12:00:00.000Z",
            project_path="/Users/kylejensen/Desktop/operator"
        )

        # Save history
        save_ingestion_history(history, history_file)

        # Reload and verify persistence
        history2 = load_ingestion_history(history_file)
        assert is_session_processed(history2, "test-smoke-123") is True
        assert is_session_processed(history2, "different-session") is False

    finally:
        history_file.unlink()


def test_fallback_matching_smoke():
    """Smoke test: Fallback matching detects duplicates by timestamp+project."""
    from packages.capture.deduplication import is_duplicate_by_timestamp_and_project

    history = {
        "processed_sessions": [
            {
                "session_id": "abc123",
                "timestamp": "2025-12-13T12:00:00.000Z",
                "project_path": "/Users/kylejensen/Desktop/operator"
            }
        ]
    }

    # Same project, close timestamp = duplicate
    assert is_duplicate_by_timestamp_and_project(
        history,
        timestamp="2025-12-13T12:02:00.000Z",
        project_path="/Users/kylejensen/Desktop/operator"
    ) is True

    # Different project = not duplicate
    assert is_duplicate_by_timestamp_and_project(
        history,
        timestamp="2025-12-13T12:02:00.000Z",
        project_path="/Users/kylejensen/Desktop/other-project"
    ) is False


def test_batch_ingestion_smoke():
    """Smoke test: Batch ingestion processes real cache directory."""
    # This is an integration smoke test - just verify script exists and is executable
    batch_script = Path(__file__).parent.parent / "scripts" / "batch_ingest_cache.py"

    assert batch_script.exists(), "Batch ingestion script missing"
    assert batch_script.stat().st_mode & 0o111, "Batch script not executable"


def test_incremental_monitor_smoke():
    """Smoke test: Incremental monitoring script exists and is configured."""
    monitor_script = Path(__file__).parent.parent / "scripts" / "monitor_cache_incremental.py"

    assert monitor_script.exists(), "Incremental monitor script missing"
    assert monitor_script.stat().st_mode & 0o111, "Monitor script not executable"


def test_launchd_plist_smoke():
    """Smoke test: launchd plist exists and has valid format."""
    plist_file = Path(__file__).parent.parent / "scripts" / "com.operator.cache-monitor.plist"

    assert plist_file.exists(), "launchd plist missing"

    # Verify it's valid XML
    with open(plist_file) as f:
        content = f.read()
        assert "<?xml" in content
        assert "com.operator.cache-monitor" in content
        assert "monitor_cache_incremental.py" in content
        assert "<integer>300</integer>" in content  # 5 minutes


def test_daily_ingestion_integration_smoke():
    """Smoke test: daily_ingestion.sh includes cache ingestion step."""
    daily_script = Path(__file__).parent.parent / "packages" / "ledger" / "scripts" / "daily_ingestion.sh"

    assert daily_script.exists(), "daily_ingestion.sh missing"

    with open(daily_script) as f:
        content = f.read()
        assert "Step 0: Cache Session Ingestion" in content
        assert "monitor_cache_incremental.py" in content
