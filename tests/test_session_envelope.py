"""
Unit tests for session envelope contract validation.

Tests cover:
- Valid session with all required fields
- Missing required top-level fields
- Missing required interaction fields
- Unknown schema versions
- Empty interactions array
- No user_prompt interactions (warning case)
- Invalid data types
"""

import pytest
import sys
from pathlib import Path

# Add packages to path for import
sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.common.session_envelope import (
    validate_session_envelope,
    REQUIRED_FIELDS,
    REQUIRED_INTERACTION_FIELDS,
    SUPPORTED_SCHEMA_VERSIONS
)


def test_valid_session_minimal():
    """Test a minimal valid session with all required fields."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": [
            {
                "id": "1",
                "type": "user_prompt",
                "timestamp": "2025-01-01T00:00:01Z",
                "content": "test message"
            }
        ]
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is True
    assert len(warnings) == 0


def test_valid_session_with_extra_fields():
    """Test that extra fields don't break validation."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "end_time": "2025-01-01T01:00:00Z",  # Extra field
        "metadata": {"foo": "bar"},  # Extra field
        "interactions": [
            {
                "id": "1",
                "type": "user_prompt",
                "timestamp": "2025-01-01T00:00:01Z",
                "content": "test",
                "role": "user",  # Extra field
                "model": "claude"  # Extra field
            }
        ]
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is True
    assert len(warnings) == 0


def test_missing_schema_version():
    """Test missing schema_version field."""
    session = {
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": []
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is False
    assert any("schema_version" in w for w in warnings)


def test_missing_session_id():
    """Test missing session_id field."""
    session = {
        "schema_version": "1.2.0",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": []
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is False
    assert any("session_id" in w for w in warnings)


def test_missing_start_time():
    """Test missing start_time field."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "interactions": []
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is False
    assert any("start_time" in w for w in warnings)


def test_missing_interactions():
    """Test missing interactions field."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z"
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is False
    assert any("interactions" in w for w in warnings)


def test_empty_interactions_array():
    """Test empty interactions array (should fail)."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": []
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is False
    assert any("empty" in w.lower() for w in warnings)


def test_interactions_not_array():
    """Test interactions field that is not an array."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": "not an array"
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is False
    assert any("array" in w.lower() for w in warnings)


def test_missing_interaction_type():
    """Test interaction missing 'type' field."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": [
            {
                "id": "1",
                "timestamp": "2025-01-01T00:00:01Z",
                "content": "test"
            }
        ]
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is False
    assert any("type" in w for w in warnings)


def test_missing_interaction_timestamp():
    """Test interaction missing 'timestamp' field."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": [
            {
                "id": "1",
                "type": "user_prompt",
                "content": "test"
            }
        ]
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is False
    assert any("timestamp" in w for w in warnings)


def test_missing_interaction_content():
    """Test interaction missing 'content' field."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": [
            {
                "id": "1",
                "type": "user_prompt",
                "timestamp": "2025-01-01T00:00:01Z"
            }
        ]
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is False
    assert any("content" in w for w in warnings)


def test_missing_interaction_id():
    """Test interaction missing 'id' field."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": [
            {
                "type": "user_prompt",
                "timestamp": "2025-01-01T00:00:01Z",
                "content": "test"
            }
        ]
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is False
    assert any("id" in w for w in warnings)


def test_unknown_schema_version_warns():
    """Test unknown schema version produces warning but still validates."""
    session = {
        "schema_version": "99.99.99",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": [
            {
                "id": "1",
                "type": "user_prompt",
                "timestamp": "2025-01-01T00:00:01Z",
                "content": "test"
            }
        ]
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is True
    assert len(warnings) == 1
    assert "99.99.99" in warnings[0]
    assert "compatibility mode" in warnings[0].lower()


def test_no_user_prompt_warns():
    """Test session with no user_prompt interactions produces warning."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": [
            {
                "id": "1",
                "type": "assistant_response",
                "timestamp": "2025-01-01T00:00:01Z",
                "content": "test"
            }
        ]
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is True
    assert len(warnings) == 1
    assert "user_prompt" in warnings[0]
    assert "Ledger" in warnings[0]


def test_multiple_interactions():
    """Test session with multiple interactions including user_prompt."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": [
            {
                "id": "1",
                "type": "user_prompt",
                "timestamp": "2025-01-01T00:00:01Z",
                "content": "First message"
            },
            {
                "id": "2",
                "type": "assistant_response",
                "timestamp": "2025-01-01T00:00:02Z",
                "content": "Response"
            },
            {
                "id": "3",
                "type": "user_prompt",
                "timestamp": "2025-01-01T00:00:03Z",
                "content": "Second message"
            }
        ]
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is True
    assert len(warnings) == 0


def test_invalid_session_type():
    """Test non-dict session input."""
    valid, warnings = validate_session_envelope("not a dict")
    assert valid is False
    assert any("object" in w.lower() or "dict" in w.lower() for w in warnings)


def test_invalid_interaction_type():
    """Test interaction that is not a dict."""
    session = {
        "schema_version": "1.2.0",
        "session_id": "abc123",
        "start_time": "2025-01-01T00:00:00Z",
        "interactions": ["not a dict"]
    }
    valid, warnings = validate_session_envelope(session)
    assert valid is False
    assert any("object" in w.lower() or "dict" in w.lower() for w in warnings)
