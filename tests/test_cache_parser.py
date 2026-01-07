"""
Tests for cache_parser.py - Parse Claude Code session cache JSONL files.

TDD Protocol: Test-first implementation of cache parser functionality.
"""

import pytest
from pathlib import Path
from packages.capture.cache_parser import parse_cache_session


def test_parse_cache_session_extracts_session_id():
    """Test cache parser extracts sessionId from JSONL file."""
    # Sample cache JSONL (simplified from real format)
    cache_file = Path(__file__).parent / "sample_data" / "cache_session_sample.jsonl"

    result = parse_cache_session(cache_file)

    # Must extract session_id from cache format
    assert "session_id" in result
    assert result["session_id"] == "0272f9fa-881c-4c28-9feb-46b17c8741f7"


def test_parse_cache_session_extracts_summary():
    """Test cache parser extracts AI-generated summary from cache."""
    cache_file = Path(__file__).parent / "sample_data" / "cache_session_sample.jsonl"

    result = parse_cache_session(cache_file)

    # First line in cache is summary
    assert "summary" in result
    assert "Ledger Query Skill" in result["summary"]


def test_parse_cache_session_extracts_timestamps():
    """Test cache parser extracts accurate session timestamps."""
    cache_file = Path(__file__).parent / "sample_data" / "cache_session_sample.jsonl"

    result = parse_cache_session(cache_file)

    # Must have start and end timestamps from actual messages
    assert "start_time" in result
    assert "end_time" in result
    assert result["start_time"] <= result["end_time"]


def test_parse_cache_session_extracts_project_context():
    """Test cache parser extracts project path and git branch."""
    cache_file = Path(__file__).parent / "sample_data" / "cache_session_sample.jsonl"

    result = parse_cache_session(cache_file)

    # Cache contains cwd and gitBranch fields
    assert "project_path" in result
    assert "git_branch" in result
    assert "/operator" in result["project_path"]
    assert result["git_branch"] == "main"


def test_parse_cache_session_returns_valid_session_envelope():
    """Test cache parser produces session envelope compatible with ingestion."""
    cache_file = Path(__file__).parent / "sample_data" / "cache_session_sample.jsonl"

    result = parse_cache_session(cache_file)

    # Must conform to session envelope schema
    required_fields = [
        "session_id",
        "summary",
        "start_time",
        "end_time",
        "project_path",
        "git_branch",
        "source",
        "source_path"
    ]

    for field in required_fields:
        assert field in result, f"Missing required field: {field}"

    assert result["source"] == "claude-code-cache"


def test_parse_codex_session_extracts_session_id():
    """Test cache parser extracts session ID from Codex JSONL format."""
    # Codex stores session_id in session_meta.payload.id
    cache_file = Path(__file__).parent / "sample_data" / "codex_session_sample.jsonl"

    result = parse_cache_session(cache_file)

    # Must extract session_id from Codex nested format
    assert "session_id" in result
    assert result["session_id"] == "019a5052-29c3-7ef2-8654-98bec284faf4"


def test_parse_codex_session_extracts_project_context():
    """Test cache parser extracts project path and git branch from Codex format."""
    cache_file = Path(__file__).parent / "sample_data" / "codex_session_sample.jsonl"

    result = parse_cache_session(cache_file)

    # Codex stores cwd in session_meta.payload.cwd
    assert "project_path" in result
    assert "Accounting OS" in result["project_path"]

    # Codex stores git branch in session_meta.payload.git.branch
    assert "git_branch" in result
    assert result["git_branch"] == "main"


def test_parse_codex_session_source_attribution():
    """Test cache parser correctly identifies Codex as source."""
    cache_file = Path(__file__).parent / "sample_data" / "codex_session_sample.jsonl"

    result = parse_cache_session(cache_file)

    # Must distinguish Codex from Claude Code sessions
    assert result["source"] == "codex-cache"


def test_parse_gemini_session_extracts_session_id():
    """Test cache parser extracts session ID from Gemini JSON format."""
    # Gemini stores session as single JSON object (not JSONL)
    cache_file = Path(__file__).parent / "sample_data" / "gemini_session_sample.json"

    result = parse_cache_session(cache_file)

    # Must extract sessionId from Gemini JSON format
    assert "session_id" in result
    assert result["session_id"] == "1822dc95-e8b6-4732-a72f-d7e216345b2e"


def test_parse_gemini_session_extracts_timestamps():
    """Test cache parser extracts timestamps from Gemini format."""
    cache_file = Path(__file__).parent / "sample_data" / "gemini_session_sample.json"

    result = parse_cache_session(cache_file)

    # Gemini has startTime and lastUpdated at top level
    assert "start_time" in result
    assert "end_time" in result
    assert result["start_time"] == "2025-12-12T19:38:08.114Z"
    assert result["end_time"] == "2025-12-12T19:39:00.363Z"


def test_parse_gemini_session_extracts_project_context():
    """Test cache parser extracts project hash from Gemini format."""
    cache_file = Path(__file__).parent / "sample_data" / "gemini_session_sample.json"

    result = parse_cache_session(cache_file)

    # Gemini stores projectHash instead of direct path
    assert "project_path" in result
    assert result["project_path"] == "dc9696f3ece1cf3dd76801a36f5724909dde40824044f86d56327c4eae2a10a8"


def test_parse_gemini_session_source_attribution():
    """Test cache parser correctly identifies Gemini as source."""
    cache_file = Path(__file__).parent / "sample_data" / "gemini_session_sample.json"

    result = parse_cache_session(cache_file)

    # Must distinguish Gemini from Claude Code and Codex sessions
    assert result["source"] == "gemini-cache"


def test_parse_gemini_session_returns_valid_session_envelope():
    """Test Gemini parser produces session envelope compatible with ingestion."""
    cache_file = Path(__file__).parent / "sample_data" / "gemini_session_sample.json"

    result = parse_cache_session(cache_file)

    # Must conform to session envelope schema
    required_fields = [
        "session_id",
        "summary",
        "start_time",
        "end_time",
        "project_path",
        "git_branch",
        "source",
        "source_path"
    ]

    for field in required_fields:
        assert field in result, f"Missing required field: {field}"

    assert result["source"] == "gemini-cache"
