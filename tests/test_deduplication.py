"""
Tests for deduplication system - Prevent duplicate evidence entries.

TDD Protocol: Test-first implementation of session ID tracking.
"""

import pytest
from pathlib import Path
from packages.capture.deduplication import (
    load_ingestion_history,
    save_ingestion_history,
    is_session_processed,
    mark_session_processed,
    extract_session_id_from_cache,
    extract_session_id_from_manual_transcript
)


def test_load_empty_ingestion_history():
    """Test loading empty ingestion history returns empty structure."""
    # Non-existent file should return empty dict
    history_file = Path("/tmp/nonexistent_history.yaml")

    result = load_ingestion_history(history_file)

    assert result == {"processed_sessions": []}


def test_mark_session_processed_adds_entry():
    """Test marking session as processed adds to history."""
    history = {"processed_sessions": []}

    mark_session_processed(
        history,
        session_id="abc123",
        source="claude-code-cache",
        source_path="/path/to/session.jsonl"
    )

    assert len(history["processed_sessions"]) == 1
    entry = history["processed_sessions"][0]
    assert entry["session_id"] == "abc123"
    assert entry["source"] == "claude-code-cache"
    assert entry["source_path"] == "/path/to/session.jsonl"
    assert "ingestion_date" in entry


def test_is_session_processed_detects_duplicate():
    """Test duplicate detection via session ID."""
    history = {
        "processed_sessions": [
            {
                "session_id": "abc123",
                "source": "claude-code-cache",
                "source_path": "/path/to/session.jsonl",
                "ingestion_date": "2025-12-08"
            }
        ]
    }

    # Same session_id should be detected as duplicate
    assert is_session_processed(history, "abc123") is True

    # Different session_id should not be duplicate
    assert is_session_processed(history, "xyz789") is False


def test_extract_session_id_from_cache():
    """Test extracting session_id from cache JSONL format."""
    cache_file = Path(__file__).parent / "sample_data" / "cache_session_sample.jsonl"

    session_id = extract_session_id_from_cache(cache_file)

    assert session_id == "0272f9fa-881c-4c28-9feb-46b17c8741f7"


def test_extract_session_id_from_manual_transcript():
    """Test extracting session_id from manual transcript JSON format."""
    # Create temp manual transcript sample
    import json
    import tempfile

    transcript_data = {
        "schema_version": "1.2.0",
        "session_id": "85c45c9f9ca7e6dd485f702a93b0ecefc45e90da71626ea555daee19552472a4",
        "start_time": "2025-10-08T21:58:21.140026+00:00"
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(transcript_data, f)
        transcript_file = Path(f.name)

    try:
        session_id = extract_session_id_from_manual_transcript(transcript_file)
        assert session_id == "85c45c9f9ca7e6dd485f702a93b0ecefc45e90da71626ea555daee19552472a4"
    finally:
        transcript_file.unlink()


def test_deduplication_prevents_re_ingestion():
    """Test full deduplication flow: ingest once, reject duplicate."""
    history = {"processed_sessions": []}
    session_id = "test-session-123"

    # First ingestion - should succeed
    assert is_session_processed(history, session_id) is False
    mark_session_processed(history, session_id, "claude-code-cache", "/path/to/file.jsonl")
    assert len(history["processed_sessions"]) == 1

    # Second ingestion - should be detected as duplicate
    assert is_session_processed(history, session_id) is True

    # Should not add duplicate entry
    prev_count = len(history["processed_sessions"])
    if not is_session_processed(history, session_id):
        mark_session_processed(history, session_id, "claude-code-cache", "/path/to/file.jsonl")

    assert len(history["processed_sessions"]) == prev_count  # No duplicate added


def test_fallback_matching_by_timestamp_and_project():
    """Test fallback matching when session_id is missing/malformed."""
    from packages.capture.deduplication import is_duplicate_by_timestamp_and_project

    history = {
        "processed_sessions": [
            {
                "session_id": "abc123",
                "source": "claude-code-cache",
                "source_path": "/Users/kylejensen/.claude/projects/-Users-kylejensen-Desktop-operator/session1.jsonl",
                "ingestion_date": "2025-12-13",
                "timestamp": "2025-12-13T12:00:00.000Z",
                "project_path": "/Users/kylejensen/Desktop/operator"
            }
        ]
    }

    # Same timestamp (within 5 minutes) + same project = duplicate
    assert is_duplicate_by_timestamp_and_project(
        history,
        timestamp="2025-12-13T12:02:00.000Z",
        project_path="/Users/kylejensen/Desktop/operator"
    ) is True

    # Different timestamp (>5 minutes) = not duplicate
    assert is_duplicate_by_timestamp_and_project(
        history,
        timestamp="2025-12-13T13:00:00.000Z",
        project_path="/Users/kylejensen/Desktop/operator"
    ) is False

    # Same timestamp but different project = not duplicate
    assert is_duplicate_by_timestamp_and_project(
        history,
        timestamp="2025-12-13T12:02:00.000Z",
        project_path="/Users/kylejensen/Desktop/other-project"
    ) is False
